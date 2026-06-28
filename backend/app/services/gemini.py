import json
import logging
import asyncio
from typing import AsyncIterator, Tuple
from app.interfaces.translation import ITranslationService
from app.core.entities import ToneType

logger = logging.getLogger("uvicorn.error")

try:
    import google.generativeai as genai
    from pydantic import BaseModel, Field
    from typing import Literal
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

if GEMINI_AVAILABLE:
    class TranslationResponseSchema(BaseModel):
        translation: str = Field(description="The localized Hindi translation of the input English text.")
        tone: Literal["formal", "casual", "excited", "urgent"] = Field(
            description="The emotional tone or level of formality of the speaker. Match based on the original audio text context."
        )

class GeminiTranslationService(ITranslationService):
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._model = None
        
        if GEMINI_AVAILABLE:
            genai.configure(api_key=self._api_key)
            # Use gemini-3.5-flash as default for fast low-latency translations
            self._model = genai.GenerativeModel("gemini-3.5-flash")

    def _parse_response(self, text: str, default_tone_type: ToneType) -> Tuple[str, str]:
        """Safely parses JSON response from Gemini, falling back to clean defaults on failure."""
        default_tone = "formal" if default_tone_type == ToneType.FORMAL else "casual"
        try:
            cleaned_text = text.strip()
            # If the response starts/ends with markdown code fences, strip them
            if cleaned_text.startswith("```"):
                lines = cleaned_text.splitlines()
                if len(lines) >= 2:
                    cleaned_text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
            
            data = json.loads(cleaned_text.strip())
            translation = data.get("translation", text)
            tone = data.get("tone", default_tone)
            
            # Clamp to allowed values
            if tone not in ["formal", "casual", "excited", "urgent"]:
                tone = default_tone
            return translation, tone
        except Exception as e:
            logger.warning(f"[Gemini Decoder] Failed to parse structured JSON translation: {e}. Falling back to default raw parser.")
            return text, default_tone

    async def translate_stream(self, text: str, tone: ToneType) -> AsyncIterator[Tuple[str, str]]:
        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai is not installed. Install requirements first or run with USE_MOCK_SERVICES=true."
            )
            
        system_instructions = (
            "You are a real-time conversational translator converting English speech to Hindi.\n"
            "Guidelines:\n"
            "1. Format dates, times, and abbreviations phonetically in localized Hindi.\n"
            "2. Keep named brand entities phonetically in Hindi script instead of translating them literally.\n"
            "3. Analyze the conversational emotion of the source English text and categorize the tone parameter in the JSON output schema.\n"
        )
        
        tone_instruction = ""
        if tone == ToneType.FORMAL:
            tone_instruction = "IMPORTANT: Default to formal and polite Hindi terms (Aap verb endings) if tone is formal.\n"
        elif tone == ToneType.CASUAL:
            tone_instruction = "IMPORTANT: Default to casual and friendly conversational Hindi terms (Tum verb endings) if tone is casual.\n"

        prompt = f"{system_instructions}\n{tone_instruction}\nTranslate this speech segment now:\n\"{text}\""
        
        config = genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=TranslationResponseSchema
        )
        
        # Async non-streaming request to guarantee output schema syntax
        response = await self._model.generate_content_async(prompt, generation_config=config)
        
        # Parse result safely
        translation, detected_tone = self._parse_response(response.text, tone)
        
        # Stream the finalized translation word-by-word with visual token pacing
        words = translation.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield chunk, detected_tone
            await asyncio.sleep(0.02) # Paced 20ms delay

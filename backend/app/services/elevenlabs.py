import httpx
import logging
from typing import AsyncIterator
from app.interfaces.tts import ITTSService
from app.core.entities import AudioOutputSegment

# Instantiate logger mapped to uvicorn console handlers
logger = logging.getLogger("uvicorn.error")

class ElevenLabsTTSService(ITTSService):
    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self._key = api_key
        # Default voice_id is "Rachel" (which supports multilingual translation), 
        # but the user can configure a custom Hindi neural voice ID
        self._voice_id = voice_id
        self._url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}/stream?optimize_streaming_latency=3"
        
        self._headers = {
            "xi-api-key": self._key,
            "Content-Type": "application/json",
            "accept": "audio/mpeg"
        }
        # Connection pooling: Instantiate a persistent client for HTTP connection keep-alive
        self._client = httpx.AsyncClient(timeout=15.0)

    async def synthesize_stream(self, text: str, tone: str = "formal") -> AsyncIterator[AudioOutputSegment]:
        # Map detected tone to ElevenLabs expressiveness parameters
        tone_settings_map = {
            "formal": {
                "stability": 0.75,
                "similarity_boost": 0.75,
                "style": 0.0,
            },
            "casual": {
                "stability": 0.50,
                "similarity_boost": 0.75,
                "style": 0.20,
            },
            "excited": {
                "stability": 0.25,
                "similarity_boost": 0.85,
                "style": 0.60,
            },
            "urgent": {
                "stability": 0.30,
                "similarity_boost": 0.75,
                "style": 0.50,
            }
        }
        
        settings = tone_settings_map.get(tone.lower(), tone_settings_map["formal"])
        
        # Formulate payload for ElevenLabs API
        # We specify 'eleven_multilingual_v2' to support high-fidelity Hindi speech output
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": settings["stability"],
                "similarity_boost": settings["similarity_boost"],
                "style": settings["style"],
                "use_speaker_boost": True
            }
        }
        
        logger.info(f"[ElevenLabs TTS] Requesting streaming audio synthesis (tone={tone}) for: \"{text}\"")

        try:
            # Trigger async stream HTTP POST request using the persistent pooled client
            async with self._client.stream(
                "POST", 
                self._url, 
                headers=self._headers, 
                json=payload
            ) as response:
                
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"[ElevenLabs TTS] API error ({response.status_code}): {error_body.decode('utf-8')}")
                    return
                
                # Yield chunks of MP3 audio bytes as they arrive from ElevenLabs (reduced chunk size for lower latency)
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    yield AudioOutputSegment(
                        audio_bytes=chunk,
                        content_type="audio/mpeg",
                        associated_text=text
                    )
        except Exception as e:
            logger.error(f"[ElevenLabs TTS] Network error during synthesis: {e}")

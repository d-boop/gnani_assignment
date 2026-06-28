import xml.etree.ElementTree as ET
import logging
from typing import AsyncIterator
import httpx
from app.interfaces.tts import ITTSService
from app.core.entities import AudioOutputSegment

# Instantiate logger mapped to uvicorn console handlers
logger = logging.getLogger("uvicorn.error")

class AzureTTSService(ITTSService):
    def __init__(self, subscription_key: str, region: str):
        self._key = subscription_key
        self._region = region
        self._url = f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self._headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/ssml+xml",
            # We output standard MP3 format. The browser client can play it natively.
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "AuraTranslate"
        }
        # Connection pooling: Instantiate a persistent client for HTTP connection keep-alive
        self._client = httpx.AsyncClient(timeout=10.0)

    async def synthesize_stream(self, text: str, tone: str = "formal") -> AsyncIterator[AudioOutputSegment]:
        # Formulate SSML (Speech Synthesis Markup Language)
        # We use a natural neural voice for Hindi: hi-IN-MadhurNeural
        ssml = (
            f"<speak version='1.0' xml:lang='hi-IN'>"
            f"<voice name='hi-IN-MadhurNeural'>"
            f"{text}"
            f"</voice>"
            f"</speak>"
        )
        
        logger.info(f"[Azure TTS] Requesting streaming audio synthesis for: \"{text}\"")

        try:
            # Trigger HTTP POST stream request using the persistent pooled client
            async with self._client.stream(
                "POST", 
                self._url, 
                headers=self._headers, 
                content=ssml.encode("utf-8")
            ) as response:
                
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"[Azure TTS] API error ({response.status_code}): {error_body.decode('utf-8')}")
                    return
                
                # Yield chunks of bytes as they arrive from the network (reduced chunk size for lower latency)
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    yield AudioOutputSegment(
                        audio_bytes=chunk,
                        content_type="audio/mpeg",
                        associated_text=text
                    )
        except Exception as e:
            logger.error(f"[Azure TTS] Network error during synthesis: {e}")

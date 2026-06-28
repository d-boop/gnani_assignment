import asyncio
import math
import struct
import time
import io
import wave
import logging
from typing import Callable, Awaitable, AsyncIterator, Tuple
from app.interfaces.asr import IASRService
from app.interfaces.translation import ITranslationService
from app.interfaces.tts import ITTSService
from app.core.entities import AudioFrame, TranscriptSegment, ToneType, AudioOutputSegment

# Instantiate logger mapped to uvicorn console handlers
logger = logging.getLogger("uvicorn.error")

class MockASRService(IASRService):
    def __init__(self):
        self._connected = False
        self._callback = None
        self._loop_task = None
        self._speaking = False
        self._last_speech_time = 0
        self._sentence_index = 0
        self._sample_buffer_size = 0
        
        self._mock_sentences = [
            "Can we move the meeting to 5 PM tomorrow?",
            "Let's check the Google Meet schedule and coordinate.",
            "Asterisk telephony integration is running smoothly.",
            "AuraTranslate uses Web Audio API and AudioWorklets in production."
        ]

    async def connect(self) -> None:
        self._connected = True
        self._last_speech_time = time.time()
        logger.info("[Mock ASR] Connected to simulated speech recognition engine.")

    async def send_audio(self, frame: AudioFrame) -> None:
        if not self._connected:
            return
        
        # Calculate Volume Intensity (RMS) of incoming raw PCM
        # 16-bit PCM = 2 bytes per sample
        byte_len = len(frame.data)
        if byte_len < 2:
            return
            
        shorts = struct.unpack(f"<{byte_len // 2}h", frame.data[:(byte_len // 2) * 2])
        if not shorts:
            return
            
        sum_squares = sum(float(s) * s for s in shorts)
        rms = math.sqrt(sum_squares / len(shorts))
        
        # Voice Activity Detection (VAD) Threshold
        # Default environment noise floor is around 100-200. Over 350 indicates speaking.
        if rms > 350:
            if not self._speaking:
                logger.info(f"[Mock ASR] Voice detected (Volume RMS: {int(rms)}). Transcription started...")
                self._speaking = True
            self._last_speech_time = time.time()
        else:
            # If silence is detected for more than 1.5 seconds after speaking, finalize translation
            if self._speaking and (time.time() - self._last_speech_time > 1.5):
                self._speaking = False
                await self._trigger_mock_transcription()

    async def receive_transcripts(self, callback: Callable[[TranscriptSegment], Awaitable[None]]) -> None:
        self._callback = callback

    async def _trigger_mock_transcription(self) -> None:
        if not self._callback:
            return
            
        # Select current mock sentence
        sentence = self._mock_sentences[self._sentence_index]
        self._sentence_index = (self._sentence_index + 1) % len(self._mock_sentences)
        
        logger.info(f"[Mock ASR] Emitting transcription: \"{sentence}\"")
        
        # Emit final transcript
        segment = TranscriptSegment(
            text=sentence,
            is_final=True,
            confidence=0.98,
            timestamp=time.time(),
            speech_final=True
        )
        await self._callback(segment)

    async def close(self) -> None:
        self._connected = False
        logger.info("[Mock ASR] Connection closed.")


class MockTranslationService(ITranslationService):
    def __init__(self):
        # Maps English mock sentences to Hindi translations
        self._mappings = {
            "Can we move the meeting to 5 PM tomorrow?": 
                "क्या हम मीटिंग को कल शाम 5 बजे कर सकते हैं?",
            "Let's check the Google Meet schedule and coordinate.": 
                "आइए गूगल मीट का शेड्यूल देखें और तालमेल बिठाएं।",
            "Asterisk telephony integration is running smoothly.": 
                "एस्टेरिस्क टेलीफोनी एकीकरण सुचारू रूप से चल रहा है।",
            "AuraTranslate uses Web Audio API and AudioWorklets in production.": 
                "ऑरा-ट्रांसलेट प्रोडक्शन में वेब ऑडियो एपीआई और ऑडियो-वर्कलेट्स का उपयोग करता है।"
        }

    async def translate_stream(self, text: str, tone: ToneType) -> AsyncIterator[Tuple[str, str]]:
        logger.info(f"[Mock Translation] Translating English sentence (Tone: {tone.value}): \"{text}\"")
        
        # Find matching mock translation or generate fallback
        hindi_translation = self._mappings.get(
            text, 
            f"[अनुवाद ({tone.value}): {text}]"
        )
        
        # Split translation into small chunks to simulate streaming tokens
        words = [w + " " for w in hindi_translation.split(" ") if w]
        if not words:
            words = [hindi_translation]
        
        for word in words:
            await asyncio.sleep(0.08) # Simulate network streaming delay (80ms per word)
            yield word, "formal"


class MockTTSService(ITTSService):
    def _generate_wav_beep(self, frequency: int = 480, duration: float = 0.5) -> bytes:
        """Helper to generate a clean 16kHz sine-wave beep in memory to simulate voice synthesis."""
        sample_rate = 16000
        num_samples = int(duration * sample_rate)
        audio_data = bytearray()
        
        # Generate raw sine wave
        for i in range(num_samples):
            t = i / sample_rate
            # Generate amplitude bound between Int16 limits
            sample = int(24000 * math.sin(2 * math.pi * frequency * t))
            # Pack as little-endian 16-bit short
            audio_data.extend(struct.pack("<h", sample))
            
        # Write wave structure to memory buffer
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_data)
            
        return wav_buf.getvalue()

    async def synthesize_stream(self, text: str, tone: str = "formal") -> AsyncIterator[AudioOutputSegment]:
        # Log using standard logger and escape hindi unicode securely for Windows CLI prints
        logger.info(f"[Mock TTS] Requesting streaming audio synthesis for: {ascii(text)}")
        
        # Generate audio beep
        beep_bytes = self._generate_wav_beep()
        
        # Yield audio segment in 2 chunks to simulate streaming back bytes
        chunk_size = len(beep_bytes) // 2
        
        for i in range(2):
            await asyncio.sleep(0.15) # Simulate audio compression & encoding delay
            chunk = beep_bytes[i * chunk_size : (i + 1) * chunk_size]
            yield AudioOutputSegment(
                audio_bytes=chunk,
                content_type="audio/wav",
                associated_text=text
            )

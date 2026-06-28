from app.core.config import settings
from app.interfaces.asr import IASRService
from app.interfaces.tts import ITTSService

# Import concrete services
from app.services.mock_services import MockASRService, MockTTSService
from app.services.deepgram import DeepgramASRService
from app.services.azure_tts import AzureTTSService
from app.services.elevenlabs import ElevenLabsTTSService

class ASRFactory:
    """Factory for creating ASR (speech-to-text) instances."""
    
    @staticmethod
    def create_asr_service() -> IASRService:
        if settings.USE_MOCK_SERVICES:
            return MockASRService()
        
        if not settings.DEEPGRAM_API_KEY:
            raise ValueError("Missing DEEPGRAM_API_KEY in configuration settings.")
            
        return DeepgramASRService(api_key=settings.DEEPGRAM_API_KEY)


class TTSFactory:
    """Factory for creating TTS (text-to-speech) instances."""
    
    @staticmethod
    def create_tts_service() -> ITTSService:
        if settings.USE_MOCK_SERVICES:
            return MockTTSService()
            
        provider = settings.TTS_PROVIDER.lower()
        
        if provider == "elevenlabs":
            if not settings.ELEVENLABS_API_KEY:
                raise ValueError("Missing ELEVENLABS_API_KEY in configuration settings.")
            return ElevenLabsTTSService(
                api_key=settings.ELEVENLABS_API_KEY,
                voice_id=settings.ELEVENLABS_VOICE_ID
            )
            
        elif provider == "azure":
            if not settings.AZURE_SPEECH_KEY:
                raise ValueError("Missing AZURE_SPEECH_KEY in configuration settings.")
            return AzureTTSService(
                subscription_key=settings.AZURE_SPEECH_KEY,
                region=settings.AZURE_SPEECH_REGION
            )
            
        else:
            raise ValueError(f"Unknown TTS service provider: '{provider}' requested.")

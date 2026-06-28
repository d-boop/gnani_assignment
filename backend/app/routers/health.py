from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    """Simple diagnostic endpoint to verify system status and loaded integrations."""
    return {
        "status": "online",
        "mock_mode": settings.USE_MOCK_SERVICES,
        "services": {
            "asr_engine": "Mocked/Simulated" if settings.USE_MOCK_SERVICES else ("Connected" if settings.DEEPGRAM_API_KEY else "Missing API Key"),
            "translation_engine": "Mocked/Simulated" if settings.USE_MOCK_SERVICES else ("Connected" if settings.GEMINI_API_KEY else "Missing API Key"),
            "tts_engine": "Mocked/Simulated" if settings.USE_MOCK_SERVICES else ("Connected" if settings.AZURE_SPEECH_KEY else "Missing API Key"),
        }
    }

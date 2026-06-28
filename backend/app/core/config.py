import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings:
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # Defaults to True to allow out-of-the-box local testing
    USE_MOCK_SERVICES: bool = os.getenv("USE_MOCK_SERVICES", "true").lower() == "true"
    
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # TTS configuration settings
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "elevenlabs") # Options: 'elevenlabs' or 'azure'
    
    AZURE_SPEECH_KEY: str = os.getenv("AZURE_SPEECH_KEY", "")
    AZURE_SPEECH_REGION: str = os.getenv("AZURE_SPEECH_REGION", "centralindia")
    
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

settings = Settings()

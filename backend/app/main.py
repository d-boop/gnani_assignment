import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import health, voice

app = FastAPI(
    title="AuraTranslate API",
    description="Real-time voice-to-voice English to Hindi translation pipeline server",
    version="1.0.0"
)

# Enable CORS for local client testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(health.router)
app.include_router(voice.router)

if __name__ == "__main__":
    print(f"Starting server on {settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "main:app", 
        host=settings.HOST, 
        port=settings.PORT, 
        reload=True
    )

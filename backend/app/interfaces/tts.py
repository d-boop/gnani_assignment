from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.core.entities import AudioOutputSegment

class ITTSService(ABC):
    """Interface for real-time Text-to-Speech (TTS) services."""

    @abstractmethod
    async def synthesize_stream(self, text: str, tone: str = "formal") -> AsyncIterator[AudioOutputSegment]:
        """Asynchronously stream output audio chunks from the TTS synthesizer with tone settings."""
        pass

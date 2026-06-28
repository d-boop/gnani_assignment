from abc import ABC, abstractmethod
from app.core.entities import AudioFrame, TranscriptSegment
from typing import Callable, Awaitable

class IASRService(ABC):
    """Interface for Automatic Speech Recognition (ASR) streaming services."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection with the remote ASR API."""
        pass

    @abstractmethod
    async def send_audio(self, frame: AudioFrame) -> None:
        """Buffer and stream raw audio data chunks to the ASR engine."""
        pass

    @abstractmethod
    async def receive_transcripts(self, callback: Callable[[TranscriptSegment], Awaitable[None]]) -> None:
        """Asynchronously listen for incoming transcripts and route them to the callback handler."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close external connection resources cleanly."""
        pass

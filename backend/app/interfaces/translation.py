from abc import ABC, abstractmethod
from typing import AsyncIterator, Tuple
from app.core.entities import ToneType

class ITranslationService(ABC):
    """Interface for streaming text translation services."""

    @abstractmethod
    async def translate_stream(self, text: str, tone: ToneType) -> AsyncIterator[Tuple[str, str]]:
        """Asynchronously stream translation tokens along with the detected tone."""
        pass

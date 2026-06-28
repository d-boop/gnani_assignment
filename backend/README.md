# AuraTranslate Backend // Architecture & Implementation Design

This document details the backend architectural design for the real-time English-to-Hindi voice-to-voice translation pipeline.

The backend is designed following **Clean Architecture**, **SOLID design principles**, and **Asynchronous Object-Oriented Programming** patterns in Python.

---

## 1. High-Level Architecture Design

The backend acts as an event-driven orchestrator that processes a continuous stream of raw audio bytes from a client, transcribes them, routes them to an LLM translator, synthesizes the translated Hindi text into speech, and streams the speech back to the client.

### Key Architectural Guidelines:
*   **Asynchronous I/O**: Because the pipeline heavily communicates with external streaming web endpoints (ASR, LLM, TTS), we use Python's `asyncio` to prevent I/O blocking.
*   **Dependency Inversion**: High-level modules (e.g., the orchestration coordinator) do not depend on low-level concrete API libraries (e.g., Deepgram SDK, Google Generative AI SDK, ElevenLabs SDK). Instead, they depend on **Abstract Interface Classes**.
*   **Decoupled Processing (Queues)**: To handle different processing speeds and network delays without data loss, we buffer data transfer between pipeline stages using isolated, session-specific `asyncio.Queue` objects.

```
                  ┌──────────────────────────────┐
                  │      Client Web Browser      │
                  └──────┬────────────────▲──────┘
                         │                │
     1. Raw PCM Ingestion│                │ 5. TTS Audio Streaming
     (WebSocket Binary)  │                │ (WebSocket Binary)
                         ▼                │
     ┌────────────────────────────────────┴──────────────────────────────────┐
     │                       FastAPI Router (voice.py)                       │
     └────────────────────────────────────┬──────────────────────────────────┘
                                          │
                  Instantiates / Coordinates (Dependency Injection)
                                          │
                                          ▼
     ┌───────────────────────────────────────────────────────────────────────┐
     │                  TranslationPipelineSession (Core)                    │
     │                                                                       │
     │  ┌──────────────────┐    ┌─────────────────┐    ┌──────────────────┐  │
     │  │  IASRService     │    │ ITranslationSvc │    │   ITTSService    │  │
     │  │  (Transcribes)   │    │  (Translates)   │    │  (Synthesizes)   │  │
     │  └────────┬─────────┘    └────────┬────────┘    └────────▲─────────┘  │
     │           │                       │                      │            │
     │           │ [Text Segment]        │ [Translated Sent.]   │ [Sentence] │
     │           ▼                       ▼                      │            │
     │     asr_queue ──────────────► asr_worker ──────────► tts_queue        │
     │                                                                       │
     └───────────────────────────────────────────────────────────────────────┘
```

---

## 2. Proposed Folder Structure

To enforce separation of concerns, the backend repository is structured into distinct layers:

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py               # Application bootstrap (initializes FastAPI, CORS, lifecycles, and loads routers)
│   │
│   ├── routers/              # HTTP and WebSocket transport controllers
│   │   ├── __init__.py
│   │   ├── health.py         # HTTP endpoint for system checks and service diagnostics
│   │   └── voice.py          # WebSocket endpoint (/stream) - coordinates connection and spawns sessions
│   │
│   ├── core/                 # Business logic and entity declarations (Core Domain)
│   │   ├── __init__.py
│   │   ├── config.py         # Environment configuration (API Keys, Server Settings)
│   │   ├── entities.py       # Domain Models (AudioFrame, TranscriptSegment, etc.)
│   │   └── orchestrator.py   # TranslationPipelineSession (coordinates concurrency and session queues)
│   │
│   ├── interfaces/           # Contract definitions (Boundaries)
│   │   ├── __init__.py
│   │   ├── asr.py            # IASRService interface definition
│   │   ├── translation.py    # ITranslationService interface definition
│   │   └── tts.py            # ITTSService interface definition
│   │
│   └── services/             # Concrete integrations / Adapters (Infrastructure)
│       ├── __init__.py
│       ├── deepgram.py       # Deepgram SDK live transcription implementation
│       ├── gemini.py         # Gemini 1.5 Pro async translation implementation
│       └── azure_tts.py      # Azure / ElevenLabs TTS streaming implementation
│
├── requirements.txt          # Python dependencies
└── README.md                 # Project instructions
```

---

## 3. Core Domain Entities

These models represent clean data scopes used throughout the application, declared in `app/core/entities.py`.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
import uuid

class ToneType(Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    AUTO = "auto"

@dataclass(frozen=True)
class AudioFrame:
    """Encapsulates raw binary audio data received from the client microphone."""
    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "linear16"

@dataclass(frozen=True)
class TranscriptSegment:
    """Represents a speech segment transcribed by the ASR system."""
    text: str
    is_final: bool
    confidence: float
    timestamp: float

@dataclass(frozen=True)
class TranslationSegment:
    """Represents a translated text segment prepared for synthesis."""
    source_text: str
    translated_text: str
    tone: ToneType
    latency_ms: float

@dataclass(frozen=True)
class AudioOutputSegment:
    """Encapsulates binary audio generated by the TTS module for client playback."""
    audio_bytes: bytes
    content_type: str = "audio/mpeg"
    associated_text: str = ""

@dataclass
class SessionContext:
    """Manages the state and conversation context of a single client pipeline connection."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    history: List[Tuple[TranscriptSegment, TranslationSegment]] = field(default_factory=list)
    default_tone: ToneType = ToneType.FORMAL
    is_active: bool = True

    def add_turn(self, transcript: TranscriptSegment, translation: TranslationSegment) -> None:
        self.history.append((transcript, translation))

    def determine_tone(self) -> ToneType:
        """Heuristic to evaluate tone based on historical inputs."""
        # Custom business rules can be added here
        return self.default_tone
```

---

## 4. Boundary Contracts (Interfaces)

These abstract base classes (`app/interfaces/`) define the interface contracts that concrete integrations must follow.

```python
# app/interfaces/asr.py
from abc import ABC, abstractmethod
from app.core.entities import AudioFrame, TranscriptSegment
from typing import Callable, Awaitable

class IASRService(ABC):
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


# app/interfaces/translation.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.core.entities import ToneType

class ITranslationService(ABC):
    @abstractmethod
    async def translate_stream(self, text: str, tone: ToneType) -> AsyncIterator[str]:
        """Stream translation tokens from the LLM translator."""
        yield


# app/interfaces/tts.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.core.entities import AudioOutputSegment

class ITTSService(ABC):
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[AudioOutputSegment]:
        """Synthesize text into raw output audio chunk streams."""
        yield
```

---

## 5. Event Orchestration Flow

1.  **WebSocket Connection**: Client opens connection `ws://localhost:8000/stream`. The router validates permissions and boots `TranslationPipelineSession`, injecting dependencies:
    ```python
    session = TranslationPipelineSession(
        asr_service=DeepgramASRService(),
        translation_service=GeminiTranslationService(),
        tts_service=AzureTTSService()
    )
    ```
2.  **Concurrency Model**: Four isolated async loops are scheduled:
    *   **Loop 1 (Socket Reader)**: Receives raw websocket binary frames (`AudioFrame`), sends to `asr_service.send_audio(frame)`.
    *   **Loop 2 (ASR Listener)**: Listens for transcript chunks. If segment `is_final` is true, routes it to the `asr_queue`.
    *   **Loop 3 (Translation Worker)**: Pulls items from `asr_queue`, kicks off streaming translation with the target tone context, batches characters into whole sentences, and places completed translation blocks in the `tts_queue`.
    *   **Loop 4 (TTS Synthesizer)**: Pulls translation text from `tts_queue`, queries the speech generator, and streams response binary bytes directly back to the client websocket.
3.  **Cancellation (Interruption)**: When the client triggers an interruption signal, the server cancels active tasks inside Loop 3 and 4, purges the `asr_queue` and `tts_queue` buffers, sends a cancellation frame to the client, and returns the pipeline context back to active waiting mode.

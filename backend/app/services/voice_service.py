import asyncio
import time
import logging
from typing import Dict, List, Optional
from fastapi import WebSocket

# Configuration & Entities
from app.core.config import settings
from app.core.entities import (
    AudioFrame, TranscriptSegment, TranslationSegment, 
    AudioOutputSegment, SessionContext, ToneType
)

# Interfaces & Factories
from app.interfaces.asr import IASRService
from app.interfaces.translation import ITranslationService
from app.interfaces.tts import ITTSService
from app.services.factories import ASRFactory, TTSFactory, TranslationFactory

# Instantiate logger mapped to uvicorn console handlers
logger = logging.getLogger("uvicorn.error")


class TranslationPipelineSession:
    """Manages the lifecycle, queues, and concurrency loops of a single active translation session."""
    
    def __init__(
        self,
        session_id: str,
        websocket: WebSocket,
        asr_service: IASRService,
        translation_service: ITranslationService,
        tts_service: ITTSService
    ):
        self.session_id = session_id
        self._websocket = websocket
        self._asr_service = asr_service
        self._translation_service = translation_service
        self._tts_service = tts_service
        
        # State
        self._context = SessionContext(session_id=session_id)
        self._running = False
        self._asr_queue = asyncio.Queue()
        self._tts_queue = asyncio.Queue()
        self._asr_buffer: List[str] = []
        self._pipeline_active = False
        
        # Async tasks references
        self._tasks: List[asyncio.Task] = []
        self._translation_task: Optional[asyncio.Task] = None
        self._tts_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Initialize connections and start the concurrent workers."""
        self._running = True
        
        # Connect to ASR engine
        await self._asr_service.connect()
        
        # Register transcript listener callback
        await self._asr_service.receive_transcripts(self._handle_transcript)
        
        # Spawn worker tasks
        self._translation_task = asyncio.create_task(self._translation_worker_loop())
        self._tts_task = asyncio.create_task(self._tts_worker_loop())
        
        self._tasks = [self._translation_task, self._tts_task]
        logger.info(f"[Session {self.session_id}] Pipeline workers successfully initialized.")
        
        # Send status event to frontend once ASR is successfully connected
        await self._send_json({
            "type": "status",
            "text": "RECORDING",
            "message": "ASR session established"
        })

    async def process_client_audio(self, data: bytes) -> None:
        """Pipe incoming raw audio chunks directly to ASR."""
        if not self._running:
            return
        frame = AudioFrame(data=data)
        await self._asr_service.send_audio(frame)

    async def handle_interruption(self) -> None:
        """Instantly purge queues and abort active translation/TTS processing loops."""
        logger.info(f"[Session {self.session_id}] Client triggered interruption. Aborting active playback.")
        
        # Cancel running workers
        if self._translation_task:
            self._translation_task.cancel()
        if self._tts_task:
            self._tts_task.cancel()

        # Purge queue contexts and buffer
        self._asr_queue = asyncio.Queue()
        self._tts_queue = asyncio.Queue()
        self._asr_buffer = []
        self._pipeline_active = False

        # Send interrupt status notification to client
        await self._send_json({
            "type": "status",
            "text": "INTERRUPTED",
            "message": "Playback aborted, ready for input."
        })

        # Re-initialize workers to listen for new inputs
        self._translation_task = asyncio.create_task(self._translation_worker_loop())
        self._tts_task = asyncio.create_task(self._tts_worker_loop())
        
        # Update references
        self._tasks = [self._translation_task, self._tts_task]

    async def _handle_transcript(self, segment: TranscriptSegment) -> None:
        """ASR Listener Callback: Routes transcript to client and queues it for translation."""
        if not self._running:
            return
            
        # Real-time server-side text-based interruption cutoff:
        # If the pipeline is active and we receive transcribed text:
        if self._pipeline_active:
            # Check if there is actual text content in this chunk
            if segment.text.strip():
                # Ignore short filler words or clicks (<= 3 characters)
                if len(segment.text.strip()) <= 3:
                    return
                # If the text is substantial (> 3 characters), trigger instant cutoff
                logger.info(f"[Session {self.session_id}] Server-initiated text interruption triggered (user spoke: \"{segment.text.strip()}\").")
                await self.handle_interruption()
            
        # Accumulate committed text segments
        if segment.is_final:
            self._asr_buffer.append(segment.text)
            cumulative_text = " ".join(self._asr_buffer).strip()
        else:
            cumulative_text = " ".join(self._asr_buffer + [segment.text]).strip()

        # Send raw cumulative transcript directly to client
        await self._send_json({
            "type": "asr",
            "text": cumulative_text,
            "is_final": segment.speech_final
        })
        
        # Only trigger translation queue when the speech is finalized by the VAD silence detector
        if segment.speech_final:
            full_text = " ".join(self._asr_buffer).strip()
            self._asr_buffer = [] # Clear buffer for next sentence turn
            
            if full_text:
                final_segment = TranscriptSegment(
                    text=full_text,
                    is_final=True,
                    confidence=segment.confidence,
                    timestamp=segment.timestamp,
                    speech_final=True
                )
                await self._asr_queue.put(final_segment)

    async def _translation_worker_loop(self) -> None:
        """Pulls final transcripts, triggers LLM translation stream, and splits into sentences."""
        try:
            while self._running:
                segment: TranscriptSegment = await self._asr_queue.get()
                
                # Activate pipeline processing flag
                self._pipeline_active = True
                
                # Send translating status back to frontend client to draw loader
                await self._send_json({
                    "type": "status",
                    "text": "TRANSLATING",
                    "message": "Translation processing started."
                })
                
                tone = self._context.determine_tone()
                start_time = time.time()
                
                accumulated_text = ""
                sentence_buffer = ""
                
                # Fetch stream generator from LLM
                stream = self._translation_service.translate_stream(segment.text, tone)
                
                detected_tone = "formal"
                async for chunk, det_tone in stream:
                    detected_tone = det_tone
                    accumulated_text += chunk
                    sentence_buffer += chunk
                    
                    # Update client UI with current streamed translation tokens
                    await self._send_json({
                        "type": "translation_stream",
                        "text": accumulated_text
                    })
                    
                    # Simple boundary check for Hindi (।), English (.), and questions (?)
                    boundaries = ["।", "?", "!", "."]
                    if any(b in chunk for b in boundaries):
                        # Sentence complete! Extract it from buffer
                        clean_sentence = sentence_buffer.strip()
                        if clean_sentence:
                            await self._tts_queue.put((clean_sentence, detected_tone))
                            sentence_buffer = ""
                
                # Push any trailing/unbounded sentence remaining in buffer
                clean_sentence = sentence_buffer.strip()
                if clean_sentence:
                    await self._tts_queue.put((clean_sentence, detected_tone))
                
                # Map detected tone safely to ToneType entity
                try:
                    seg_tone = ToneType(detected_tone)
                except ValueError:
                    seg_tone = ToneType.AUTO
                
                # Complete the segment record
                translation_segment = TranslationSegment(
                    source_text=segment.text,
                    translated_text=accumulated_text,
                    tone=seg_tone,
                    latency_ms=(time.time() - start_time) * 1000
                )
                self._context.add_turn(segment, translation_segment)
                
                # Finalize output translation text and send total latency metrics
                await self._send_json({
                    "type": "translation",
                    "text": accumulated_text,
                    "latency": int(translation_segment.latency_ms)
                })
                
                self._asr_queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"[Session {self.session_id}] Translation worker canceled.")
        except Exception as e:
            logger.error(f"[Session {self.session_id}] Error in Translation worker: {e}")

    async def _tts_worker_loop(self) -> None:
        """Pulls translated text sentences and streams generated audio chunks to client WebSocket."""
        try:
            while self._running:
                queue_item = await self._tts_queue.get()
                if isinstance(queue_item, tuple):
                    sentence, tone = queue_item
                else:
                    sentence, tone = queue_item, "formal"
                
                logger.info(f"[TTS Worker] Routing sentence (tone={tone}) for speech synthesis: \"{sentence}\"")
                
                # Stream audio bytes from TTS
                try:
                    tts_stream = self._tts_service.synthesize_stream(sentence, tone)
                    async for audio_segment in tts_stream:
                        # Write binary audio packet out directly to client WS
                        if self._running:
                            await self._websocket.send_bytes(audio_segment.audio_segment if hasattr(audio_segment, "audio_segment") else audio_segment.audio_bytes)
                except Exception as e:
                    logger.error(f"[Session {self.session_id}] TTS stream failed: {e}")
                
                # Notify the client that the audio stream for this sentence has ended
                if self._running:
                    await self._send_json({
                        "type": "audio_end"
                    })
                
                # Turn is complete: release pipeline lock
                self._pipeline_active = False
                
                self._tts_queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"[Session {self.session_id}] TTS worker canceled.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"[Session {self.session_id}] Error in TTS worker: {e}")

    async def close(self) -> None:
        """Clean up connection nodes and terminate active loops."""
        self._running = False
        self._asr_buffer = []
        self._pipeline_active = False
        
        # Terminate workers
        for task in self._tasks:
            task.cancel()
            
        # Close ASR service connection
        await self._asr_service.close()
        logger.info(f"[Session {self.session_id}] Session pipeline terminated.")

    async def _send_json(self, data: dict) -> None:
        """Helper to send JSON response to the client socket safely."""
        try:
            await self._websocket.send_json(data)
        except Exception as e:
            logger.error(f"[Session {self.session_id}] Failed to send WebSocket message: {e}")
            self._running = False


class VoiceService:
    """Facade class mapping application operations to underlying session managers."""
    
    def __init__(self):
        self._active_sessions: Dict[str, TranslationPipelineSession] = {}

    async def start_session(self, session_id: str, websocket: WebSocket) -> None:
        """Resolves dependencies using factories and boots pipeline workers for a connection."""
        logger.info(f"[VoiceService] Initializing session: {session_id}")
        
        # 1. Resolve ASR and TTS instances via Factories
        asr_service = ASRFactory.create_asr_service()
        tts_service = TTSFactory.create_tts_service()
        
        # 2. Resolve Translation instance via Factory
        translation_service = TranslationFactory.create_translation_service()

        # 3. Instantiate session object
        session = TranslationPipelineSession(
            session_id=session_id,
            websocket=websocket,
            asr_service=asr_service,
            translation_service=translation_service,
            tts_service=tts_service
        )
        
        # 4. Start execution loops
        await session.start()
        
        # 5. Store session mapping
        self._active_sessions[session_id] = session

    async def process_audio(self, session_id: str, data: bytes) -> None:
        """Forwards incoming audio buffer bytes to the targeted session."""
        session = self._active_sessions.get(session_id)
        if session:
            await session.process_client_audio(data)

    async def trigger_interruption(self, session_id: str) -> None:
        """Triggers the interruption purge sequences for the targeted session."""
        session = self._active_sessions.get(session_id)
        if session:
            await session.handle_interruption()

    async def terminate_session(self, session_id: str) -> None:
        """Closes and deletes the session cleanly from the facade maps."""
        session = self._active_sessions.pop(session_id, None)
        if session:
            await session.close()

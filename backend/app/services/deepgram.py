import asyncio
import json
import logging
import time
from typing import Callable, Awaitable
import websockets
from app.interfaces.asr import IASRService
from app.core.entities import AudioFrame, TranscriptSegment

# Instantiate logger mapped to uvicorn console handlers
logger = logging.getLogger("uvicorn.error")

class DeepgramASRService(IASRService):
    """Deepgram ASR Service communicating directly via standard websockets."""
    
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._ws = None
        self._callback = None
        self._listen_task = None
        self._running = False

    async def connect(self) -> None:
        self._running = True
        headers = {"Authorization": f"Token {self._api_key}"}
        url = (
            "wss://api.deepgram.com/v1/listen"
            "?model=nova-2"
            "&language=en-US"
            "&encoding=linear16"
            "&sample_rate=16000"
            "&channels=1"
            "&interim_results=true"
            "&utterance_end_ms=1500"
            "&endpointing=2000"
            "&punctuation=false"
        )
        
        try:
            self._ws = await websockets.connect(url, additional_headers=headers)
            logger.info("[Deepgram ASR] Live session successfully connected via direct WebSocket.")
            
            # Start background listener task in uvicorn's main async event loop
            self._listen_task = asyncio.create_task(self._listen_loop())
        except Exception as e:
            logger.error(f"[Deepgram ASR] Failed to connect direct WebSocket: {e}")
            raise e

    async def _listen_loop(self) -> None:
        """Listener loop running on the main asyncio thread to receive transcripts."""
        try:
            async for message in self._ws:
                if not self._running:
                    break
                data = json.loads(message)
                
                # Catch native Deepgram UtteranceEnd event
                if data.get("type") == "UtteranceEnd":
                    logger.info("[Deepgram ASR] UtteranceEnd event received (silence pause detected).")
                    if self._callback:
                        segment = TranscriptSegment(
                            text="",
                            is_final=True,
                            confidence=1.0,
                            timestamp=time.time(),
                            speech_final=True
                        )
                        await self._callback(segment)
                    continue
                
                # Check for transcript structure in the reply
                channel = data.get("channel", {})
                
                # Robust parsing: handle if channel is a list or dictionary
                if isinstance(channel, list):
                    channel_data = channel[0] if len(channel) > 0 else {}
                else:
                    channel_data = channel
                    
                if not isinstance(channel_data, dict):
                    continue
                    
                alternatives = channel_data.get("alternatives", [])
                if not alternatives:
                    continue
                    
                transcript = alternatives[0].get("transcript", "")
                is_final = data.get("is_final", False)
                speech_final = data.get("speech_final", False)
                confidence = alternatives[0].get("confidence", 0.0)
                
                if transcript:
                    logger.info(f"[Deepgram ASR] Transcript: \"{transcript}\" (final={is_final}, speech_final={speech_final})")
                    
                    if self._callback:
                        segment = TranscriptSegment(
                            text=transcript,
                            is_final=is_final,
                            confidence=confidence,
                            timestamp=time.time(),
                            speech_final=speech_final
                        )
                        await self._callback(segment)
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[Deepgram ASR] Direct WebSocket connection closed: {e}")
        except Exception as e:
            logger.error(f"[Deepgram ASR] Error in direct WebSocket listen loop: {e}")

    async def send_audio(self, frame: AudioFrame) -> None:
        if self._ws and self._running:
            try:
                await self._ws.send(frame.data)
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                logger.error(f"[Deepgram ASR] Failed to send audio: {e}")

    async def receive_transcripts(self, callback: Callable[[TranscriptSegment], Awaitable[None]]) -> None:
        self._callback = callback

    async def close(self) -> None:
        self._running = False
        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.info("[Deepgram ASR] Direct WebSocket session closed.")

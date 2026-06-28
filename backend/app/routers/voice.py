import json
import uuid
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.voice_service import VoiceService

router = APIRouter()

# Instantiate logger mapped to uvicorn console handlers
logger = logging.getLogger("uvicorn.error")

# Instantiate the Voice Service Facade
voice_service = VoiceService()

@router.websocket("/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    """WebSocket endpoint to capture microphone audio and stream back translated voice."""
    # Establish raw connection socket handshake
    await websocket.accept()
    
    session_id = str(uuid.uuid4())[:8]
    logger.info(f"[WebSocket] Accepted client connection. Session ID: {session_id}")

    try:
        # 1. Initialize and start session via VoiceService Facade
        await voice_service.start_session(session_id, websocket)
        
        # 2. Continuous socket listening loop
        while True:
            message = await websocket.receive()
            
            # Break if disconnect message was received
            if message.get("type") == "websocket.disconnect":
                break
                
            # Route raw voice chunk binary data
            if "bytes" in message:
                await voice_service.process_audio(session_id, message["bytes"])
                
            # Route JSON command string parameters
            elif "text" in message:
                try:
                    payload = json.loads(message["text"])
                    if payload.get("type") == "interrupt":
                        await voice_service.trigger_interruption(session_id)
                except json.JSONDecodeError:
                    pass
                    
    except WebSocketDisconnect:
        logger.info(f"[WebSocket] Session {session_id} connection disconnected by client.")
        
    except Exception as e:
        import traceback
        # Send error payload if connection is still alive
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server processing error: {str(e)}"
            })
        except Exception:
            pass
        logger.error(f"[WebSocket] Session {session_id} run loop failed: {e}")
        traceback.print_exc()
        
    finally:
        # 3. Clean up active pipeline loops and connections via VoiceService Facade
        await voice_service.terminate_session(session_id)

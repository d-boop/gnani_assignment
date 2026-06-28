import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from app.services.voice_service import TranslationPipelineSession
from app.services.mock_services import MockASRService, MockTranslationService, MockTTSService

class TestTranslationPipeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create an async mock for the FastAPI WebSocket client
        self.mock_websocket = AsyncMock()
        self.mock_websocket.send_json = AsyncMock()
        self.mock_websocket.send_bytes = AsyncMock()
        
        # Instantiate services
        self.asr_service = MockASRService()
        self.translation_service = MockTranslationService()
        self.tts_service = MockTTSService()
        
        # Instantiate coordinator session
        self.session = TranslationPipelineSession(
            session_id="test_session",
            websocket=self.mock_websocket,
            asr_service=self.asr_service,
            translation_service=self.translation_service,
            tts_service=self.tts_service
        )

    async def test_pipeline_startup_and_processing(self):
        # 1. Start pipeline workers
        await self.session.start()
        self.assertTrue(self.session._running)
        
        # 2. Simulate user speaking (Volume RMS > 350)
        # We write high-amplitude values in a loop to trigger Voice Activity Detection (VAD)
        # 1000 samples of alternate positive/negative large values (simulates voice)
        voice_pcm_chunk = bytearray()
        for i in range(1000):
            sample = 25000 if i % 2 == 0 else -25000
            import struct
            voice_pcm_chunk.extend(struct.pack("<h", sample))
            
        await self.session.process_client_audio(bytes(voice_pcm_chunk))
        
        # Allow the mock VAD mechanism to process the audio buffer
        await asyncio.sleep(0.5)
        
        # 3. Simulate client silent pause to trigger transcription
        # Real clients stream continuously even during silence. We stream silence frames for 2.2s.
        for _ in range(22):
            silence_chunk = b"\x00\x00" * 800
            await self.session.process_client_audio(silence_chunk)
            await asyncio.sleep(0.1)
        
        # Verify transcription output was sent to client WebSocket
        calls = self.mock_websocket.send_json.call_args_list
        asr_updates = [c for c in calls if c[0][0].get("type") == "asr"]
        translation_updates = [c for c in calls if c[0][0].get("type") == "translation"]
        
        # We expect at least one finalized transcript and translation
        self.assertTrue(len(asr_updates) > 0, "ASR transcriptions should have been emitted")
        self.assertTrue(len(translation_updates) > 0, "Translation response should have been emitted")
        
        # 4. Verify binary TTS output chunks were sent to the client
        self.assertTrue(self.mock_websocket.send_bytes.called, "Binary TTS voice segments should have been streamed")
        
        # Tear down session
        await self.session.close()

    async def test_pipeline_interruption(self):
        await self.session.start()
        
        # Queue up mock text for processing
        await self.session._asr_queue.put(
            MagicMock(text="Wait a second...", is_final=True)
        )
        
        # Immediately trigger user interruption
        await self.session.handle_interruption()
        
        # The queues should be empty, and interrupt status sent to client
        self.assertTrue(self.session._asr_queue.empty())
        self.assertTrue(self.session._tts_queue.empty())
        
        calls = self.mock_websocket.send_json.call_args_list
        interrupt_calls = [c for c in calls if c[0][0].get("text") == "INTERRUPTED"]
        self.assertTrue(len(interrupt_calls) > 0, "INTERRUPTED status should be sent to client")
        
        await self.session.close()


class TestVoiceServiceFacade(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.config import settings
        settings.USE_MOCK_SERVICES = True # Force mock mode for testing
        
        from app.services.voice_service import VoiceService
        self.voice_service = VoiceService()
        self.mock_websocket = AsyncMock()

    async def test_session_lifecycle_facade(self):
        session_id = "facade_test"
        
        # Start session via Facade
        await self.voice_service.start_session(session_id, self.mock_websocket)
        self.assertIn(session_id, self.voice_service._active_sessions)
        
        # Process some silence audio
        await self.voice_service.process_audio(session_id, b"\x00\x00" * 800)
        
        # Trigger interruption via Facade
        await self.voice_service.trigger_interruption(session_id)
        
        # Terminate session via Facade
        await self.voice_service.terminate_session(session_id)
        self.assertNotIn(session_id, self.voice_service._active_sessions)


if __name__ == "__main__":
    unittest.main()

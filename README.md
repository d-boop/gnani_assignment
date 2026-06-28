# Gnani Voice Translator 🎙️🤖

Gnani Voice Translator is a high-speed, real-time conversational voice translator that transcribes English speech input, translates it dynamically to Hindi (with emotion/tone classification), and streams back synthesized Hindi speech output with matching emotional inflection.

It utilizes a low-latency, server-controlled loop that processes audio, handles live interruptions instantly using character-length safety gates, and operates on clean, SOLID-compliant service factories.

---

## Architecture & Features

1.  **ASR (Speech-to-Text)**: Powered by **Deepgram Nova-2** WebSocket streaming. Captures raw client microphone buffers and returns real-time text chunks.
2.  **LLM Translation**: Powered by Google **Gemini 1.5/2.5** (utilizing the fastest available model `gemini-flash-lite-latest` on your API key). Translates English to Devanagari Hindi and dynamically classifies the emotional tone (`formal`, `casual`, `excited`, `urgent`).
3.  **TTS (Text-to-Speech)**: Powered by **ElevenLabs** or **Azure Speech Services**. Modulates voice parameters (stability, style, pitch) based on the LLM's detected tone to generate expressive, emotional speech streams.
4.  **Low-Latency Interruption**: A server-controlled interruption loop. The moment you start speaking while the robot is talking, it cancels active tasks and stops playback.
5.  **Noise-Filtering Gate**: Filters interruptions on text length (`len > 3`). Accidental mic clicks, keyboard taps, or short breath filler words (like `"uh"`, `"i"`) are ignored, preventing false cutoffs.
6.  **SOLID Factories**: Completely decoupled using the Dependency Inversion Principle. Components instantiate dynamically based on environment configuration mappings.

---

## Setup & Installation

### Prerequisites
*   Python 3.10 or higher
*   Node.js (for the static dev web server)

---

### 1. Backend Configuration

1.  Navigate to the backend directory:
    ```bash
    cd backend
    ```
2.  Create a virtual environment:
    ```bash
    python -m venv venv
    ```
3.  Activate the virtual environment:
    *   **Windows (PowerShell)**:
        ```powershell
        .\venv\Scripts\Activate.ps1
        ```
    *   **macOS / Linux**:
        ```bash
        source venv/bin/activate
        ```
4.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5.  Create a `.env` file in the `backend/` directory and configure the environment variables (see below).

---

### 2. Frontend Configuration

1.  Navigate to the frontend directory:
    ```bash
    cd ../frontend
    ```
2.  Ensure your browser microphone permissions are enabled. The frontend uses standard Web Audio APIs to sample mic input.

---

## Configuration Variables (`backend/.env`)

Create a `.env` file in the `backend/` folder. The following keys are supported:

| Key | Description | Default |
| :--- | :--- | :--- |
| `USE_MOCK_SERVICES` | Set to `false` to use real APIs, or `true` to run locally without internet API keys. | `true` |
| `ASR_PROVIDER` | The active speech-to-text service. | `deepgram` |
| `DEEPGRAM_API_KEY` | Deepgram API Key (required if mock is false). | `(your-key)` |
| `TRANSLATION_PROVIDER` | The active LLM translation service. | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API Key (required if mock is false). | `(your-key)` |
| `TTS_PROVIDER` | The active text-to-speech service (`elevenlabs` or `azure`). | `elevenlabs` |
| `ELEVENLABS_API_KEY` | ElevenLabs API Key (required if Elevenlabs TTS is chosen). | `(your-key)` |
| `ELEVENLABS_VOICE_ID` | ElevenLabs Voice ID model reference. | `ErXwobaYiN019PkySvjV` |
| `AZURE_SPEECH_KEY` | Azure Speech subscription key (required if Azure TTS is chosen). | `(your-key)` |
| `AZURE_SPEECH_REGION` | Azure Speech Services region (e.g. `centralindia`). | `centralindia` |

---

## Running the Application

### Step 1: Start the Backend Server
From the `backend/` directory (with virtual environment active):
```bash
python -m uvicorn app.main:app --port 8000
```
*The WebSocket stream endpoint will open on `ws://localhost:8000/stream`.*

### Step 2: Start the Frontend Web Server
From the `frontend/` directory in a new terminal window:
```bash
node server.js
```
*The static page dev server will boot on `http://localhost:3000`.*

### Step 3: Test in Browser
1.  Open **`http://localhost:3000`** in Google Chrome or Edge.
2.  Click **START CAPTURE** and grant microphone access.
3.  Speak a sentence in English (e.g. *"Hello, what are you doing?"*).
4.  Confirm translation appears on the screen, and synthesized Hindi audio starts playing back.
5.  To test interruption, say `"stop"` loud and clear while the robot is speaking. Playback will halt instantly!

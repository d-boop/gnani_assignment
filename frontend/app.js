// State Management
let audioContext = null;
let mediaStream = null;
let audioSource = null;
let processorNode = null;
let analyserNode = null;
let animationFrameId = null;
let websocket = null;
let isRecording = false;
let isMockMode = false;
let waitingForNewSpeech = false;

// Streaming Audio Player State
let receivedAudioChunks = [];
let audioPlaybackQueue = [];
let isPlayingAudio = false;
let currentAudio = null;

function playNextAudioInQueue() {
  if (isPlayingAudio || audioPlaybackQueue.length === 0) return;
  isPlayingAudio = true;
  
  const audioUrl = audioPlaybackQueue.shift();
  console.log("[Player] Playing audio segment:", audioUrl);
  currentAudio = new Audio(audioUrl);
  
  currentAudio.onended = () => {
    console.log("[Player] Segment playback ended.");
    URL.revokeObjectURL(audioUrl);
    isPlayingAudio = false;
    currentAudio = null;
    playNextAudioInQueue();
  };
  
  currentAudio.onerror = (err) => {
    console.error("[Player] Segment playback error:", err);
    URL.revokeObjectURL(audioUrl);
    isPlayingAudio = false;
    currentAudio = null;
    playNextAudioInQueue();
  };

  currentAudio.play().then(() => {
    console.log("[Player] Playback started successfully.");
  }).catch(err => {
    console.error('[Player] Playback invocation failed:', err);
    URL.revokeObjectURL(audioUrl);
    isPlayingAudio = false;
    currentAudio = null;
    playNextAudioInQueue();
  });
}

// DOM Elements
const toggleRecordBtn = document.getElementById('toggle-record-btn');
const btnText = toggleRecordBtn.querySelector('.btn-text');
const pipelineStatus = document.getElementById('pipeline-status');
const websocketStatus = document.getElementById('websocket-status');
const visualizerPanel = document.querySelector('.visualizer-panel');
const asrText = document.getElementById('asr-text');
const transText = document.getElementById('trans-text');
const latencyVal = document.getElementById('latency-val');

// Visualizer Bars
const bars = [
  document.getElementById('bar-1'),
  document.getElementById('bar-2'),
  document.getElementById('bar-3'),
  document.getElementById('bar-4'),
  document.getElementById('bar-5')
];

// Event Listeners
toggleRecordBtn.addEventListener('click', handleToggleRecord);

// WebSocket Setup
function initWebSocket() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Connect directly to the FastAPI backend running on port 8000
  const wsUrl = `${wsProtocol}//localhost:8000/stream`;

  websocketStatus.textContent = 'WS: CONNECTING...';
  
  websocket = new WebSocket(wsUrl);
  websocket.binaryType = 'arraybuffer';

  websocket.onopen = () => {
    console.log('WebSocket connected successfully');
    websocketStatus.textContent = 'WS: CONNECTED';
    websocketStatus.style.color = '#ff6a00';
    isMockMode = false;
  };

  websocket.onmessage = (event) => {
    // Handle binary audio chunks from TTS
    if (event.data instanceof ArrayBuffer) {
      console.log(`[Client] Received TTS audio chunk: ${event.data.byteLength} bytes`);
      receivedAudioChunks.push(event.data);
      return;
    }
    
    // Handle JSON metadata
    try {
      const data = JSON.parse(event.data);
      console.log("[Client] Received JSON message:", data);
      handleServerResponse(data);
    } catch (err) {
      console.warn('Received non-JSON message from backend:', event.data);
    }
  };

  websocket.onerror = (error) => {
    console.error('WebSocket connection error:', error);
  };

  websocket.onclose = () => {
    console.log('WebSocket connection closed.');
    websocketStatus.textContent = 'WS: OFFLINE (SIMULATED)';
    websocketStatus.style.color = '#828fa1';
    // Fall back to local simulation mode so visualizer still functions
    isMockMode = true;
  };
}

// Toggle recording state
async function handleToggleRecord() {
  if (isRecording) {
    stopRecording();
  } else {
    try {
      await startRecording();
    } catch (err) {
      console.error('Failed to start recording:', err);
      alert('Could not access microphone. Make sure you grant permission and are running on localhost/HTTPS.');
    }
  }
}

// Start audio context & recording pipeline
async function startRecording() {
  // 1. Initialize AudioContext at 16kHz for automatic client-side downsampling
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  audioContext = new AudioContextClass({ sampleRate: 16000 });
  
  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }

  // 2. Request microphone stream
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }
  });

  // 3. Connect audio source
  audioSource = audioContext.createMediaStreamSource(mediaStream);

  // 4. Load AudioWorklet module
  await audioContext.audioWorklet.addModule('audio-processor.js');

  // 5. Initialize AnalyserNode for local real-time visualization
  analyserNode = audioContext.createAnalyser();
  analyserNode.fftSize = 64; // Smaller FFT size for cleaner vocal range mapping
  
  // 6. Initialize AudioWorkletNode
  processorNode = new AudioWorkletNode(audioContext, 'audio-processor');

  // 7. Connect Graph
  audioSource.connect(analyserNode);
  audioSource.connect(processorNode);

  // 8. Handle output binary PCM data
  processorNode.port.onmessage = (event) => {
    const rawPcm = event.data; // ArrayBuffer (16-bit PCM)
    
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(rawPcm);
    } else if (isMockMode) {
      // Print debug logs in simulation mode
      console.log(`[Simulation] Sent PCM buffer chunk to WebSocket: ${rawPcm.byteLength} bytes`);
    }
  };

  // Connect to server (re-establish WebSocket connection on start)
  initWebSocket();

  // Update UI state to "Setting Up"
  isRecording = false; // Stay false until backend is ready
  toggleRecordBtn.disabled = true; // Disable temporarily to prevent multiple quick clicks during handshake
  toggleRecordBtn.classList.remove('btn-start');
  toggleRecordBtn.classList.add('btn-stop');
  btnText.textContent = 'SETTING UP...';
  
  visualizerPanel.classList.add('active');
  pipelineStatus.textContent = 'PIPELINE: SETTING UP';
  const statusDot = document.querySelector('.status-dot');
  statusDot.classList.add('active');

  // Clear placeholder text entirely on capture start
  asrText.innerHTML = '';
  transText.innerHTML = '';
  waitingForNewSpeech = false;
}

// Stop audio context & recording pipeline
function stopRecording() {
  isRecording = false;

  // Stop and clear audio playback
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  audioPlaybackQueue = [];
  receivedAudioChunks = [];
  isPlayingAudio = false;

  // Stop visualizer animation loop
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
  }

  // Close audio context nodes
  if (processorNode) {
    processorNode.disconnect();
    processorNode = null;
  }
  
  if (audioSource) {
    audioSource.disconnect();
    audioSource = null;
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  // Close WebSocket
  if (websocket) {
    websocket.close();
    websocket = null;
  }

  // Reset visualizer bars
  bars.forEach(bar => {
    bar.style.transform = 'scaleY(0.2)';
  });

  // Reset UI elements
  toggleRecordBtn.disabled = false;
  toggleRecordBtn.classList.remove('btn-stop');
  toggleRecordBtn.classList.add('btn-start');
  btnText.textContent = 'START CAPTURE';

  visualizerPanel.classList.remove('active');
  pipelineStatus.textContent = 'PIPELINE: IDLE';
  const statusDot = document.querySelector('.status-dot');
  statusDot.classList.remove('active');

  // Restore placeholders when recording stops
  asrText.innerHTML = '<span class="text-placeholder">Awaiting speech input...</span>';
  transText.innerHTML = '<span class="text-placeholder">अनुवाद की प्रतीक्षा की जा रही है...</span>';
  waitingForNewSpeech = false;
}

// Frequency-domain visualizer updates
function drawVisualizer() {
  if (!isRecording || !analyserNode) return;

  animationFrameId = requestAnimationFrame(drawVisualizer);

  const bufferLength = analyserNode.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  analyserNode.getByteFrequencyData(dataArray);

  // Split vocal-range frequencies across the 5 visualization bars
  const mappings = [
    dataArray[2] || 0, // Bass
    dataArray[4] || 0, // Mid-low
    dataArray[7] || 0, // Mid
    dataArray[10] || 0, // Mid-high
    dataArray[14] || 0  // Treble
  ];

  bars.forEach((bar, index) => {
    // Normalize frequency magnitude (0 - 255) to scaling factor (0.2 to 2.4)
    const val = mappings[index];
    const scale = 0.2 + (val / 255) * 2.2;
    bar.style.transform = `scaleY(${scale})`;
  });
}

// Handle transcription & translation socket replies from real backend
function handleServerResponse(response) {
  if (response.latency) {
    latencyVal.textContent = `LATENCY: ${response.latency} MS`;
  }
  
  if (response.type === 'asr') {
    // Speech-to-Text Update (ignore empty or space-only updates)
    const cleanText = response.text ? response.text.trim() : '';
    if (cleanText) {
      // Clear previous translation ONLY when user begins speaking a fresh sentence
      if (waitingForNewSpeech) {
        transText.innerHTML = '';
        waitingForNewSpeech = false;
      }
      asrText.textContent = response.text;
    }
    
    // Once the user stops speaking (ASR finalized), wait for server to start translating
    if (response.is_final) {
      waitingForNewSpeech = true;
    }
    
    // Trigger client-side interruption to cut off playback if user starts speaking fresh sentences
    if (!response.is_final && isPlayingAudio && response.text && response.text.trim().length > 3) {
      console.log("[Client] User interrupted. Cutting off local playback.");
      websocket.send(JSON.stringify({ type: "interrupt" }));
      if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
      }
      audioPlaybackQueue = [];
      receivedAudioChunks = [];
      isPlayingAudio = false;
    }
  } else if (response.type === 'translation_stream') {
    // Streaming Translation Update (word-by-word)
    if (response.text && response.text.trim()) {
      transText.textContent = response.text;
    }
  } else if (response.type === 'translation') {
    // Finalized Translation Sentence
    if (response.text && response.text.trim()) {
      transText.textContent = response.text;
    }
  } else if (response.type === 'audio_end') {
    console.log(`[Client] Audio transmission ended. Assembling ${receivedAudioChunks.length} chunks.`);
    if (receivedAudioChunks.length > 0) {
      const audioBlob = new Blob(receivedAudioChunks, { type: 'audio/mpeg' });
      receivedAudioChunks = []; // Clear buffer for next sentence
      
      const audioUrl = URL.createObjectURL(audioBlob);
      console.log("[Client] Created playback Blob URL:", audioUrl);
      audioPlaybackQueue.push(audioUrl);
      playNextAudioInQueue();
    } else {
      console.warn("[Client] Received audio_end but receivedAudioChunks is empty!");
    }
  } else if (response.type === 'status' && response.text === 'INTERRUPTED') {
    // Server confirmed interruption cleanup
    console.log("[Client] Server confirmed interruption.");
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    audioPlaybackQueue = [];
    receivedAudioChunks = [];
    isPlayingAudio = false;
  } else if (response.type === 'status' && response.text === 'TRANSLATING') {
    // Server confirmed translation processing started, draw loader
    console.log("[Client] Server started translating. Drawing loader.");
    transText.innerHTML = '<div class="translation-loader"><span></span><span></span><span></span></div>';
    waitingForNewSpeech = true;
  } else if (response.type === 'status' && response.text === 'RECORDING') {
    console.log("[Client] Backend ASR successfully established. Arming microphone capture.");
    isRecording = true;
    toggleRecordBtn.disabled = false;
    btnText.textContent = 'STOP CAPTURE';
    pipelineStatus.textContent = 'PIPELINE: RECORDING';
    
    // Start visualizer rendering loop now that capture is armed!
    drawVisualizer();
  }
}



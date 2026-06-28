class AudioProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0]; // Take the first channel (mono)

      // Convert Float32Array to 16-bit Signed Integer PCM
      const int16Buffer = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        // Clamp float values to avoid distortion [-1.0, 1.0]
        const sample = Math.max(-1.0, Math.min(1.0, channelData[i]));
        int16Buffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }

      // Send the raw ArrayBuffer back to the main thread.
      // Use transferable objects ([int16Buffer.buffer]) for zero-copy performance.
      this.port.postMessage(int16Buffer.buffer, [int16Buffer.buffer]);
    }
    return true; // Keep the processor alive
  }
}

registerProcessor('audio-processor', AudioProcessor);

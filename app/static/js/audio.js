/**
 * Audio Engine: Web Audio API, Microphone Capture, Sample-Accurate PCM Streaming Playback,
 * Jitter Buffer, and Dynamic Canvas Visualizer.
 */

class AudioEngine {
  constructor() {
    this.audioCtx = null;
    this.playbackAnalyser = null;
    this.micAnalyser = null;
    this.analyser = null; // Alias to active analyser
    this.streamGainNode = null;
    this.mediaStream = null;
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.sourceNode = null;
    this.scriptProcessor = null;
    this.recMuteGain = null;
    this.recordedPcmBuffers = [];
    this.isRecording = false;

    // Continuous Voice Activity Detection (VAD) & Conversation Session State
    this.isContinuousListening = false;
    this.isSpeechActive = false;
    this.vadPaused = false;
    this.ambientFloor = 0.005;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
    this.speechBuffers = [];
    this.preRollBuffers = [];
    this.maxPreRoll = 3;
    this.speechStartTime = 0;
    this.silenceStartTime = 0;
    this.vadSilenceTimeoutMs = 650;
    this.vadMinSpeechDurationMs = 280;
    this.bargeInFrames = 0;
    this.playbackStartTime = 0;
    this.bargeInMode = 'voice'; // 'voice' = auto-detect speech, 'manual' = click-only interrupt
    this.bargeInThreshold = 0.12; // Realistic voice threshold to prevent speaker self-interruption
    this.bargeInRequiredFrames = 5; // ~420ms of sustained speech required to interrupt
    this.bargeInGracePeriodMs = 600; // Ignore mic for first 600ms of playback startup
    this.onVadSpeechStart = null;
    this.onVadSpeechEnd = null;
    this.onVadBargeIn = null;
    this.onVadVolumeChange = null;

    // Streaming Playback State (Sample-Accurate Web Audio Timeline)
    this.streamSampleRate = 24000;
    this.streamChannels = 1;
    this.nextStartTime = 0;
    this.scheduledNodes = [];
    this.isStreaming = false;
    this.streamEnded = false;
    this.isPlaying = false;
    this.pcmRemainderByte = null; // Remainder byte carryover for odd chunk boundaries
    this.streamChunkCount = 0; // Chunks received in current stream (container sniffing on first only)

    // Jitter Pre-buffering to absorb network packet arrival jitter
    this.isPrebuffering = false;
    this.jitterBuffer = [];
    this.jitterBufferedDuration = 0;
    this.prebufferTargetDuration = 0.08; // 80ms jitter buffer ensures gapless playback

    // Container / Fallback playback
    this.currentContainerSource = null;

    // Canvas Visualizer
    this.canvas = null;
    this.canvasCtx = null;
    this.animationId = null;
    this.visualizerMode = 'idle'; // 'idle', 'recording', 'playing'

    this.onRecordingStart = null;
    this.onRecordingStop = null;
    this.onPlaybackEnd = null;
  }

  async initAudioContext() {
    if (!this.audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioContextClass();

      // Playback analyser connected to speakers for voice visualization
      this.playbackAnalyser = this.audioCtx.createAnalyser();
      this.playbackAnalyser.fftSize = 256;
      this.playbackAnalyser.smoothingTimeConstant = 0.8;

      // Microphone analyser ISOLATED from speakers (never connected to destination)
      // This prevents user microphone audio from echoing back into speakers/headphones
      this.micAnalyser = this.audioCtx.createAnalyser();
      this.micAnalyser.fftSize = 256;
      this.micAnalyser.smoothingTimeConstant = 0.8;

      this.analyser = this.playbackAnalyser;

      // Master stream gain node with smooth fading capability
      this.streamGainNode = this.audioCtx.createGain();
      this.streamGainNode.gain.setValueAtTime(1.0, this.audioCtx.currentTime);

      this.streamGainNode.connect(this.playbackAnalyser);
      this.playbackAnalyser.connect(this.audioCtx.destination);
    }

    if (this.audioCtx.state === 'suspended') {
      await this.audioCtx.resume();
    }
  }

  attachCanvas(canvasElement) {
    this.canvas = canvasElement;
    this.canvasCtx = canvasElement.getContext('2d');
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());
    this.startVisualizerLoop();
  }

  resizeCanvas() {
    if (this.canvas) {
      this.canvas.width = this.canvas.offsetWidth * window.devicePixelRatio;
      this.canvas.height = this.canvas.offsetHeight * window.devicePixelRatio;
      this.canvasCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }
  }

  // --- Microphone Recording (WAV PCM 16-bit 16kHz) ---
  async startRecording() {
    await this.initAudioContext();
    this.stopPlayback(false);

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
      // Connect to micAnalyser for real-time visualizer canvas ONLY (never to speakers)
      this.sourceNode.connect(this.micAnalyser);

      // Capture raw Float32 microphone PCM audio
      this.recordedPcmBuffers = [];
      this.isRecording = true;
      this.scriptProcessor = this.audioCtx.createScriptProcessor(4096, 1, 1);
      this.scriptProcessor.onaudioprocess = (e) => {
        if (!this.isRecording) return;
        const inputData = e.inputBuffer.getChannelData(0);
        this.recordedPcmBuffers.push(new Float32Array(inputData));
      };

      this.sourceNode.connect(this.scriptProcessor);
      // In Web Audio specifications, ScriptProcessorNode requires a downstream connection to process audio.
      // We route it through a completely muted GainNode (gain = 0.0) into destination.
      // This strictly guarantees ZERO echo or feedback into the user's speakers or headphones.
      this.recMuteGain = this.audioCtx.createGain();
      this.recMuteGain.gain.setValueAtTime(0.0, this.audioCtx.currentTime);
      this.scriptProcessor.connect(this.recMuteGain);
      this.recMuteGain.connect(this.audioCtx.destination);

      this.visualizerMode = 'recording';

      if (this.onRecordingStart) this.onRecordingStart();
      return true;
    } catch (err) {
      console.error('Error accessing microphone:', err);
      let userFriendlyMsg = 'Microphone access failed: ' + (err.message || 'unknown error');
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        userFriendlyMsg = 'Microphone access is blocked. Please allow microphone access in your browser settings and try again.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        userFriendlyMsg = 'No microphone was detected on your system. Please connect an audio input device and try again.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        userFriendlyMsg = 'Microphone is already in use by another application. Please free your audio device and try again.';
      }
      throw new Error(userFriendlyMsg);
    }
  }

  async stopRecording() {
    this.isRecording = false;
    this.visualizerMode = 'idle';

    if (this.scriptProcessor) {
      this.scriptProcessor.onaudioprocess = null;
      try { this.scriptProcessor.disconnect(); } catch (e) {}
      this.scriptProcessor = null;
    }
    if (this.recMuteGain) {
      try { this.recMuteGain.disconnect(); } catch (e) {}
      this.recMuteGain = null;
    }
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch (e) {}
      this.sourceNode = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }

    if (!this.recordedPcmBuffers || this.recordedPcmBuffers.length === 0) {
      if (this.onRecordingStop) this.onRecordingStop(null);
      return null;
    }

    // Merge Float32Array chunks into a continuous PCM buffer
    const totalSamples = this.recordedPcmBuffers.reduce((sum, b) => sum + b.length, 0);
    const merged = new Float32Array(totalSamples);
    let offset = 0;
    let sumSquares = 0;
    for (const buf of this.recordedPcmBuffers) {
      merged.set(buf, offset);
      offset += buf.length;
    }
    this.recordedPcmBuffers = [];

    // Calculate RMS energy to detect silence or near-zero background noise
    for (let i = 0; i < merged.length; i++) {
      sumSquares += merged[i] * merged[i];
    }
    const rms = Math.sqrt(sumSquares / Math.max(1, merged.length));

    // Reject recordings under 0.25s or purely silent (RMS < 0.002)
    const inputSampleRate = this.audioCtx.sampleRate || 44100;
    const durationSeconds = merged.length / inputSampleRate;
    if (durationSeconds < 0.25 || rms < 0.002) {
      console.log(`[AudioEngine] Audio discarded: duration=${durationSeconds.toFixed(2)}s, RMS=${rms.toFixed(5)} (Silence)`);
      if (this.onRecordingStop) this.onRecordingStop(null);
      return null;
    }

    const targetSampleRate = 16000;
    const downsampled = this.downsampleBuffer(merged, inputSampleRate, targetSampleRate);
    const wavBlob = this.encodeWav(downsampled, targetSampleRate);

    if (this.onRecordingStop) this.onRecordingStop(wavBlob);
    return wavBlob;
  }

  // --- Continuous Voice Activity Detection (VAD) & Conversation Session Mode ---
  async startContinuousListening({
    onSpeechStart = null,
    onSpeechEnd = null,
    onBargeIn = null,
    onVolumeChange = null,
    silenceTimeoutMs = 1050,
    minSpeechDurationMs = 380,
  } = {}) {
    await this.initAudioContext();

    this.onVadSpeechStart = onSpeechStart;
    this.onVadSpeechEnd = onSpeechEnd;
    this.onVadBargeIn = onBargeIn;
    this.onVadVolumeChange = onVolumeChange;
    this.vadSilenceTimeoutMs = silenceTimeoutMs;
    this.vadMinSpeechDurationMs = minSpeechDurationMs;

    this.isContinuousListening = true;
    this.isSpeechActive = false;
    this.vadPaused = false;
    this.ambientFloor = 0.005;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
    this.speechBuffers = [];
    this.preRollBuffers = [];
    this.maxPreRoll = 3;
    this.speechStartTime = 0;
    this.silenceStartTime = 0;
    this.bargeInFrames = 0;

    if (!this.mediaStream) {
      try {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      } catch (err) {
        console.error('Error accessing microphone:', err);
        let userFriendlyMsg = 'Microphone access failed: ' + (err.message || 'unknown error');
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          userFriendlyMsg = 'Microphone access is blocked. Please allow microphone access in your browser settings and try again.';
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          userFriendlyMsg = 'No microphone was detected on your system. Please connect an audio input device and try again.';
        } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
          userFriendlyMsg = 'Microphone is already in use by another application. Please free your audio device and try again.';
        }
        throw new Error(userFriendlyMsg);
      }
    }

    if (!this.sourceNode) {
      this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
      this.sourceNode.connect(this.micAnalyser);
    }

    if (this.scriptProcessor) {
      try {
        this.scriptProcessor.onaudioprocess = null;
        this.scriptProcessor.disconnect();
      } catch (_) {}
      this.scriptProcessor = null;
    }

    this.scriptProcessor = this.audioCtx.createScriptProcessor(4096, 1, 1);
    this.scriptProcessor.onaudioprocess = (e) => {
      this.processContinuousAudioFrame(e);
    };

    this.sourceNode.connect(this.scriptProcessor);

    if (!this.recMuteGain) {
      this.recMuteGain = this.audioCtx.createGain();
      this.recMuteGain.gain.setValueAtTime(0.0, this.audioCtx.currentTime);
      this.scriptProcessor.connect(this.recMuteGain);
      this.recMuteGain.connect(this.audioCtx.destination);
    } else {
      this.scriptProcessor.connect(this.recMuteGain);
    }

    this.visualizerMode = 'recording';
    return true;
  }

  processContinuousAudioFrame(e) {
    if (!this.isContinuousListening) return;

    const inputData = e.inputBuffer.getChannelData(0);
    const frame = new Float32Array(inputData);
    const now = performance.now();

    // Calculate RMS energy of this audio frame (~85-93ms)
    let sumSq = 0;
    for (let i = 0; i < frame.length; i++) {
      sumSq += frame[i] * frame[i];
    }
    const rms = Math.sqrt(sumSq / frame.length);

    if (this.onVadVolumeChange) {
      this.onVadVolumeChange(rms);
    }

    // 1. Natural Interruption / Barge-In while assistant is actively speaking
    if (this.isPlaying) {
      // Manual mode: voice barge-in disabled, user must click the interrupt button
      if (this.bargeInMode === 'manual') {
        return;
      }

      // Grace period: ignore mic input for first N ms of playback to let
      // hardware echo cancellation stabilise and prevent self-interruption
      const playbackElapsed = now - this.playbackStartTime;
      if (playbackElapsed < this.bargeInGracePeriodMs) {
        this.bargeInFrames = 0;
        return;
      }

      // Dynamic threshold: inspect real-time speaker playback output via playbackAnalyser
      // to ensure speaker audio cannot trip the detector
      let speakerRms = 0;
      if (this.playbackAnalyser) {
        try {
          const pcmData = new Float32Array(this.playbackAnalyser.fftSize);
          this.playbackAnalyser.getFloatTimeDomainData(pcmData);
          let pSum = 0;
          for (let i = 0; i < pcmData.length; i++) {
            pSum += pcmData[i] * pcmData[i];
          }
          speakerRms = Math.sqrt(pSum / pcmData.length);
        } catch (_) {}
      }

      // If speakers are outputting sound, threshold must scale above speaker bleed
      const dynamicThreshold = Math.max(
        this.bargeInThreshold,
        speakerRms * 1.5,
        this.ambientFloor * 3.5
      );

      if (rms > dynamicThreshold) {
        this.bargeInFrames = (this.bargeInFrames || 0) + 1;
        if (this.bargeInFrames >= this.bargeInRequiredFrames) {
          console.log(`[AudioEngine] Barge-In: Sustained user voice detected (RMS=${rms.toFixed(4)}, speakerRms=${speakerRms.toFixed(4)}, threshold=${dynamicThreshold.toFixed(4)}, frames=${this.bargeInFrames}). Halting assistant.`);
          this.bargeInFrames = 0;
          this.stopPlayback(true);
          if (this.onVadBargeIn) {
            this.onVadBargeIn();
          }
        }
      } else {
        this.bargeInFrames = 0;
      }
      return;
    }

    // 2. If VAD is paused (processing STT or waiting for AI), discard frames
    if (this.vadPaused) {
      return;
    }

    // 3. Dynamic ambient noise floor adaptation
    if (!this.isSpeechActive) {
      this.ambientFloor = this.ambientFloor * 0.95 + rms * 0.05;
      // Maintain pre-roll ring buffer (~270ms) to ensure initial word onset isn't clipped
      this.preRollBuffers.push(frame);
      if (this.preRollBuffers.length > this.maxPreRoll) {
        this.preRollBuffers.shift();
      }
    }

    const speechThreshold = Math.max(0.012, this.ambientFloor * 2.5);
    const silenceThreshold = Math.max(0.006, speechThreshold * 0.72);

    // 4. Voice Activity State Transitions
    if (rms > speechThreshold) {
      this.consecutiveSpeechFrames++;
      this.consecutiveSilenceFrames = 0;
      this.silenceStartTime = 0;

      // Onset detection: Require 2 consecutive frames (~180ms) above threshold to filter transient clicks
      if (!this.isSpeechActive && this.consecutiveSpeechFrames >= 2) {
        this.isSpeechActive = true;
        this.speechStartTime = now;
        this.speechBuffers = [...this.preRollBuffers, frame];
        this.preRollBuffers = [];
        console.log(`[AudioEngine] Speech started (RMS=${rms.toFixed(4)}, Threshold=${speechThreshold.toFixed(4)})`);
        if (this.onVadSpeechStart) {
          this.onVadSpeechStart();
        }
      } else if (this.isSpeechActive) {
        this.speechBuffers.push(frame);
      }
    } else if (this.isSpeechActive) {
      // User was speaking; this frame is below speech threshold
      this.speechBuffers.push(frame);

      if (rms < silenceThreshold) {
        this.consecutiveSilenceFrames++;
        if (this.silenceStartTime === 0) {
          this.silenceStartTime = now;
        }

        const silenceElapsed = now - this.silenceStartTime;
        const totalSpeechElapsed = now - this.speechStartTime;

        // End of speech triggered when silence duration exceeded
        if (silenceElapsed >= this.vadSilenceTimeoutMs) {
          console.log(`[AudioEngine] End-of-speech detected: silence=${silenceElapsed.toFixed(0)}ms, speech=${totalSpeechElapsed.toFixed(0)}ms.`);
          this.isSpeechActive = false;
          this.consecutiveSpeechFrames = 0;
          this.consecutiveSilenceFrames = 0;
          this.silenceStartTime = 0;

          const collected = this.speechBuffers;
          this.speechBuffers = [];

          if (totalSpeechElapsed >= this.vadMinSpeechDurationMs && collected.length > 0) {
            const wavBlob = this.packagePcmBuffersToWav(collected);
            if (this.onVadSpeechEnd) {
              this.onVadSpeechEnd(wavBlob);
            }
          } else {
            console.log(`[AudioEngine] Transient sound ignored (${totalSpeechElapsed.toFixed(0)}ms < ${this.vadMinSpeechDurationMs}ms).`);
          }
        }
      } else {
        // Brief pause between words
        this.silenceStartTime = 0;
        this.consecutiveSilenceFrames = 0;
      }
    }
  }

  packagePcmBuffersToWav(buffers) {
    if (!buffers || buffers.length === 0) return null;
    const totalSamples = buffers.reduce((sum, b) => sum + b.length, 0);
    const merged = new Float32Array(totalSamples);
    let offset = 0;
    for (const buf of buffers) {
      merged.set(buf, offset);
      offset += buf.length;
    }
    const inputSampleRate = this.audioCtx ? this.audioCtx.sampleRate : 44100;
    const targetSampleRate = 16000;
    const downsampled = this.downsampleBuffer(merged, inputSampleRate, targetSampleRate);
    return this.encodeWav(downsampled, targetSampleRate);
  }

  pauseVad() {
    this.vadPaused = true;
    this.isSpeechActive = false;
    this.speechBuffers = [];
    this.preRollBuffers = [];
    this.silenceStartTime = 0;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
  }

  resumeVad() {
    this.vadPaused = false;
    this.isSpeechActive = false;
    this.speechBuffers = [];
    this.preRollBuffers = [];
    this.silenceStartTime = 0;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
    if (this.isContinuousListening) {
      this.visualizerMode = 'recording';
    }
  }

  /**
   * Set the barge-in (interruption) mode.
   * @param {'voice'|'manual'} mode
   *   'voice'  - Automatically detect sustained user speech and interrupt the assistant.
   *   'manual' - Disable voice-based interruption; the user must click the Interrupt button.
   */
  setBargeInMode(mode) {
    this.bargeInMode = (mode === 'manual') ? 'manual' : 'voice';
    console.log(`[AudioEngine] Barge-in mode set to: ${this.bargeInMode}`);
  }

  stopContinuousListening() {
    this.isContinuousListening = false;
    this.isSpeechActive = false;
    this.vadPaused = false;
    this.speechBuffers = [];
    this.preRollBuffers = [];
    this.silenceStartTime = 0;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;

    if (this.scriptProcessor) {
      try {
        this.scriptProcessor.onaudioprocess = null;
        this.scriptProcessor.disconnect();
      } catch (_) {}
      this.scriptProcessor = null;
    }

    if (this.recMuteGain) {
      try { this.recMuteGain.disconnect(); } catch (_) {}
      this.recMuteGain = null;
    }

    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch (_) {}
      this.sourceNode = null;
    }

    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      } catch (_) {}
      this.mediaStream = null;
    }

    this.visualizerMode = 'idle';
  }

  downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
    if (outputSampleRate >= inputSampleRate) {
      return buffer;
    }
    const sampleRateRatio = inputSampleRate / outputSampleRate;
    const newLength = Math.round(buffer.length / sampleRateRatio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
      let accum = 0;
      let count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = count > 0 ? accum / count : 0;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }

  encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };

    /* RIFF identifier */
    writeString(0, 'RIFF');
    /* file length (36 + data length) */
    view.setUint32(4, 36 + samples.length * 2, true);
    /* RIFF type */
    writeString(8, 'WAVE');
    /* format chunk identifier */
    writeString(12, 'fmt ');
    /* format chunk length */
    view.setUint32(16, 16, true);
    /* sample format (raw 1 = PCM) */
    view.setUint16(20, 1, true);
    /* channel count (1 = mono) */
    view.setUint16(22, 1, true);
    /* sample rate */
    view.setUint32(24, sampleRate, true);
    /* byte rate (sampleRate * 1 channel * 2 bytes) */
    view.setUint32(28, sampleRate * 2, true);
    /* block align (1 channel * 2 bytes) */
    view.setUint16(32, 2, true);
    /* bits per sample (16-bit) */
    view.setUint16(34, 16, true);
    /* data chunk identifier */
    writeString(36, 'data');
    /* data chunk length */
    view.setUint32(40, samples.length * 2, true);

    // Write 16-bit signed PCM samples (-32768 to 32767)
    let index = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      index += 2;
    }

    return new Blob([view], { type: 'audio/wav' });
  }

  // --- Streaming Audio Playback Queue (Sample-Accurate PCM) ---
  async startStreamingPlayback(sampleRate = 24000, channels = 1) {
    await this.initAudioContext();

    // Stop any previously playing audio immediately
    this.stopPlayback(false);

    this.streamSampleRate = sampleRate;
    this.streamChannels = channels;
    this.isStreaming = true;
    this.streamEnded = false;
    this.isPlaying = true;
    this.playbackStartTime = performance.now();
    this.visualizerMode = 'playing';

    this.pcmRemainderByte = null;
    this.scheduledNodes = [];
    this.nextStartTime = 0;
    this.streamChunkCount = 0;

    // Initialize jitter prebuffering
    this.isPrebuffering = true;
    this.jitterBuffer = [];
    this.jitterBufferedDuration = 0;

    // Reset stream gain node
    if (this.streamGainNode) {
      this.streamGainNode.gain.cancelScheduledValues(this.audioCtx.currentTime);
      this.streamGainNode.gain.setValueAtTime(1.0, this.audioCtx.currentTime);
    }
  }

  async queueAudioChunk(arrayBuffer) {
    if (!arrayBuffer || arrayBuffer.byteLength === 0) return;
    await this.initAudioContext();

    const uint8 = new Uint8Array(arrayBuffer);

    // Only the first chunk of a stream can be a container file (WAV/MP3/OGG
    // header). Later chunks are raw PCM payloads whose sample bytes may
    // coincidentally match a container/codec magic signature — decoding one as
    // a container would drop audio and kill the scheduled playback.
    if (this.streamChunkCount === 0 && this.isContainerFormat(uint8)) {
      this.streamChunkCount += 1;
      await this.playContainerAudio(arrayBuffer);
      return;
    }

    // Process raw 16-bit PCM chunk with sample-accurate scheduling
    this.streamChunkCount += 1;
    this.processPcmChunk(uint8);
  }

  processPcmChunk(uint8) {
    let data = uint8;

    // 1. Prepend any leftover byte from the previous chunk
    if (this.pcmRemainderByte !== null) {
      const combined = new Uint8Array(data.length + 1);
      combined[0] = this.pcmRemainderByte;
      combined.set(data, 1);
      data = combined;
      this.pcmRemainderByte = null;
    }

    // 2. If length is odd, save trailing byte for next chunk to guarantee 16-bit alignment
    if (data.length % 2 !== 0) {
      this.pcmRemainderByte = data[data.length - 1];
      data = data.subarray(0, data.length - 1);
    }

    if (data.length === 0) return;

    // 3. Convert 16-bit Little-Endian signed PCM to Float32 [-1.0, 1.0]
    const numSamples = data.length / 2;
    const dataView = new DataView(data.buffer, data.byteOffset, data.byteLength);
    const float32 = new Float32Array(numSamples);

    for (let i = 0; i < numSamples; i++) {
      const int16 = dataView.getInt16(i * 2, true); // Little-endian
      float32[i] = int16 < 0 ? int16 / 32768.0 : int16 / 32767.0;
    }

    // 4. Create Web Audio buffer for this chunk
    const audioBuffer = this.audioCtx.createBuffer(
      this.streamChannels || 1,
      numSamples,
      this.streamSampleRate || 24000
    );
    audioBuffer.getChannelData(0).set(float32);

    // 5. Jitter Buffer Pre-buffering: accumulate ~80ms before scheduling to absorb network jitter
    if (this.isPrebuffering) {
      this.jitterBuffer.push(audioBuffer);
      this.jitterBufferedDuration += audioBuffer.duration;

      if (
        this.jitterBufferedDuration >= this.prebufferTargetDuration ||
        this.jitterBuffer.length >= 3
      ) {
        this.flushJitterBuffer();
      }
      return;
    }

    this.scheduleAudioBuffer(audioBuffer);
  }

  flushJitterBuffer() {
    this.isPrebuffering = false;
    const chunks = this.jitterBuffer;
    this.jitterBuffer = [];
    this.jitterBufferedDuration = 0;

    for (const buf of chunks) {
      this.scheduleAudioBuffer(buf);
    }
  }

  scheduleAudioBuffer(audioBuffer) {
    if (!this.audioCtx) return;

    const now = this.audioCtx.currentTime;

    // If nextStartTime is in the past (stream beginning or network underrun):
    // Anchor nextStartTime slightly in the future (25ms lead time) for seamless staging
    if (this.nextStartTime < now) {
      this.nextStartTime = now + 0.025;
    }

    const source = this.audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.streamGainNode || this.analyser);

    source.start(this.nextStartTime);
    this.nextStartTime += audioBuffer.duration;

    this.scheduledNodes.push(source);
    this.isPlaying = true;
    this.visualizerMode = 'playing';

    source.onended = () => {
      const idx = this.scheduledNodes.indexOf(source);
      if (idx !== -1) {
        this.scheduledNodes.splice(idx, 1);
      }
      this.checkPlaybackEnd();
    };
  }

  endStreamingPlayback() {
    this.streamEnded = true;

    // Flush any pending jitter buffer (e.g. for short single-phrase replies)
    if (this.isPrebuffering) {
      this.flushJitterBuffer();
    }

    this.pcmRemainderByte = null;
    this.checkPlaybackEnd();
  }

  checkPlaybackEnd() {
    if (
      this.streamEnded &&
      this.scheduledNodes.length === 0 &&
      this.jitterBuffer.length === 0
    ) {
      this.isPlaying = false;
      this.isStreaming = false;
      this.visualizerMode = this.isContinuousListening ? 'recording' : 'idle';
      if (this.onPlaybackEnd) this.onPlaybackEnd();
    }
  }

  stopPlayback(fade = true) {
    this.isStreaming = false;
    this.streamEnded = true;
    this.isPrebuffering = false;
    this.jitterBuffer = [];
    this.jitterBufferedDuration = 0;
    this.pcmRemainderByte = null;
    this.streamChunkCount = 0;
    this.nextStartTime = 0;

    const nodesToStop = [...this.scheduledNodes];
    this.scheduledNodes = [];

    if (fade && this.streamGainNode && this.audioCtx && this.audioCtx.state === 'running') {
      try {
        // Fast 25ms micro-ramp down to prevent speaker click on interruption
        const now = this.audioCtx.currentTime;
        this.streamGainNode.gain.cancelScheduledValues(now);
        this.streamGainNode.gain.setValueAtTime(this.streamGainNode.gain.value, now);
        this.streamGainNode.gain.linearRampToValueAtTime(0.0001, now + 0.025);

        setTimeout(() => {
          for (const node of nodesToStop) {
            try {
              node.stop();
              node.disconnect();
            } catch (_) {}
          }
          if (this.streamGainNode && this.audioCtx) {
            this.streamGainNode.gain.setValueAtTime(1.0, this.audioCtx.currentTime);
          }
        }, 30);
      } catch (_) {
        for (const node of nodesToStop) {
          try {
            node.stop();
            node.disconnect();
          } catch (_) {}
        }
      }
    } else {
      for (const node of nodesToStop) {
        try {
          node.stop();
          node.disconnect();
        } catch (_) {}
      }
    }

    if (this.currentContainerSource) {
      try {
        this.currentContainerSource.stop();
        this.currentContainerSource.disconnect();
      } catch (_) {}
      this.currentContainerSource = null;
    }

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }

    this.isPlaying = false;
    this.visualizerMode = this.isContinuousListening ? 'recording' : 'idle';
  }

  speakTextWithBrowser(text, onStart = null, onEnd = null) {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      console.warn('[AudioEngine] Browser SpeechSynthesis not supported.');
      if (onEnd) onEnd();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(
      (v) =>
        v.lang.startsWith('en') &&
        (v.name.includes('Natural') ||
          v.name.includes('Google') ||
          v.name.includes('Neural') ||
          v.name.includes('Samantha') ||
          v.name.includes('David') ||
          v.name.includes('Zira'))
    );
    if (naturalVoice) utterance.voice = naturalVoice;

    this.isPlaying = true;
    this.visualizerMode = 'playing';

    utterance.onstart = () => {
      this.isPlaying = true;
      this.visualizerMode = 'playing';
      if (onStart) onStart();
    };
    utterance.onend = () => {
      this.isPlaying = false;
      this.visualizerMode = this.isContinuousListening ? 'recording' : 'idle';
      if (onEnd) onEnd();
      if (this.onPlaybackEnd) this.onPlaybackEnd();
    };
    utterance.onerror = (e) => {
      this.isPlaying = false;
      this.visualizerMode = this.isContinuousListening ? 'recording' : 'idle';
      if (onEnd) onEnd();
      if (this.onPlaybackEnd) this.onPlaybackEnd();
    };
    window.speechSynthesis.speak(utterance);
  }

  // --- Container Format Inspection & Fallback Playback ---
  isContainerFormat(uint8) {
    if (uint8.length < 4) return false;
    // RIFF (WAV)
    if (uint8[0] === 0x52 && uint8[1] === 0x49 && uint8[2] === 0x46 && uint8[3] === 0x46) return true;
    // ID3 (MP3 tag)
    if (uint8[0] === 0x49 && uint8[1] === 0x44 && uint8[2] === 0x33) return true;
    // OGG (OggS)
    if (uint8[0] === 0x4F && uint8[1] === 0x67 && uint8[2] === 0x67 && uint8[3] === 0x53) return true;
    // MP3 Sync frame header (0xFF 0xFB, 0xFF 0xF3, 0xFF 0xF2)
    if (uint8[0] === 0xFF && (uint8[1] === 0xFB || uint8[1] === 0xF3 || uint8[1] === 0xF2)) return true;
    return false;
  }

  async playContainerAudio(arrayBuffer) {
    try {
      const audioBuffer = await this.audioCtx.decodeAudioData(arrayBuffer.slice(0));
      this.stopPlayback(false);

      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.streamGainNode || this.analyser);
      this.currentContainerSource = source;

      this.isPlaying = true;
      this.visualizerMode = 'playing';

      source.onended = () => {
        if (this.currentContainerSource === source) {
          this.currentContainerSource = null;
          this.isPlaying = false;
          this.visualizerMode = 'idle';
        }
      };

      source.start(0);
    } catch (err) {
      console.warn('Error decoding container audio:', err);
    }
  }

  async playBlob(blob) {
    if (!blob) return;
    await this.initAudioContext();
    const arrayBuffer = await blob.arrayBuffer();
    await this.playContainerAudio(arrayBuffer);
  }

  playChime(type) {
    if (!this.audioCtx) return;
    try {
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
      const now = this.audioCtx.currentTime;

      if (type === 'start') {
        // Subtle dual-tone rising chime (520Hz -> 680Hz)
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(520, now);
        osc.frequency.exponentialRampToValueAtTime(680, now + 0.1);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.18);
      } else if (type === 'listening') {
        // Clean soft pulse (640Hz)
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(640, now);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.09);
      } else if (type === 'interrupt') {
        // Soft downward blip (440Hz -> 300Hz)
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(300, now + 0.08);
        gain.gain.setValueAtTime(0.07, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.12);
      }
    } catch (_) {}
  }

  // --- Dynamic Waveform & Particle Visualizer Loop ---
  startVisualizerLoop() {
    const dataArray = new Uint8Array(128);

    // Dynamic ember particles
    const particles = Array.from({ length: 28 }, () => ({
      x: Math.random(),
      y: Math.random(),
      radius: Math.random() * 2 + 0.8,
      speedX: (Math.random() - 0.5) * 0.0015,
      speedY: -Math.random() * 0.002 - 0.0005,
      alpha: Math.random() * 0.5 + 0.2,
    }));

    const draw = () => {
      this.animationId = requestAnimationFrame(draw);
      if (!this.canvas || !this.canvasCtx) return;

      const width = this.canvas.offsetWidth;
      const height = this.canvas.offsetHeight;
      const ctx = this.canvasCtx;

      ctx.clearRect(0, 0, width, height);

      let values = [];
      const activeAnalyser =
        this.visualizerMode === 'recording'
          ? this.micAnalyser
          : this.visualizerMode === 'playing'
          ? this.playbackAnalyser
          : null;

      if (activeAnalyser) {
        activeAnalyser.getByteFrequencyData(dataArray);
        values = Array.from(dataArray);
      } else {
        // Idle breathing sine wave
        values = Array(64).fill(0);
      }

      // Calculate audio energy [0..1]
      const avgEnergy = values.reduce((a, b) => a + b, 0) / (values.length * 255 || 1);

      // 1. Draw Background Radial Glow Aura
      const centerY = height / 2;
      const auraGradient = ctx.createRadialGradient(
        width / 2, centerY, 10,
        width / 2, centerY, Math.max(width / 3, 120) * (1 + avgEnergy * 0.8)
      );
      if (this.visualizerMode === 'playing') {
        auraGradient.addColorStop(0, 'rgba(245, 208, 97, 0.22)');
        auraGradient.addColorStop(1, 'rgba(212, 175, 55, 0)');
      } else if (this.visualizerMode === 'recording') {
        auraGradient.addColorStop(0, 'rgba(74, 222, 128, 0.15)');
        auraGradient.addColorStop(1, 'rgba(74, 222, 128, 0)');
      } else {
        auraGradient.addColorStop(0, 'rgba(245, 208, 97, 0.08)');
        auraGradient.addColorStop(1, 'rgba(212, 175, 55, 0)');
      }
      ctx.fillStyle = auraGradient;
      ctx.fillRect(0, 0, width, height);

      // 2. Draw Floating Particle Embers
      particles.forEach((p) => {
        p.x += p.speedX * (1 + avgEnergy * 2);
        p.y += p.speedY * (1 + avgEnergy * 2);
        if (p.y < 0) { p.y = 1; p.x = Math.random(); }
        if (p.x < 0) p.x = 1;
        if (p.x > 1) p.x = 0;

        ctx.beginPath();
        ctx.arc(p.x * width, p.y * height, p.radius * (1 + avgEnergy), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(245, 208, 97, ${p.alpha * (0.35 + avgEnergy * 0.65)})`;
        ctx.fill();
      });

      // 3. Draw Multi-Sine Glow Wave
      const time = Date.now() * 0.003;

      // Layer 1: Warm Gold Luminous Sine Wave
      ctx.beginPath();
      ctx.lineWidth = 3.2;
      ctx.strokeStyle = this.visualizerMode === 'recording' ? '#F8D877' : '#F5D061';
      ctx.shadowBlur = 22;
      ctx.shadowColor =
        this.visualizerMode === 'recording'
          ? 'rgba(248, 216, 119, 0.85)'
          : 'rgba(245, 208, 97, 0.75)';

      for (let x = 0; x < width; x += 4) {
        const index = Math.floor((x / width) * 40);
        const amp = (values[index] || 10) / 255;
        const wave = Math.sin(x * 0.015 + time) * (amp * 48 + 6);
        const y = centerY + wave;

        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Layer 2: Warm Sand Ivory Harmonic Wave
      ctx.beginPath();
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = '#FAF6F0';
      ctx.shadowBlur = 14;
      ctx.shadowColor = 'rgba(250, 246, 240, 0.65)';

      for (let x = 0; x < width; x += 4) {
        const index = Math.floor((x / width) * 40);
        const amp = (values[index] || 10) / 255;
        const wave = Math.cos(x * 0.02 - time * 0.8) * (amp * 36 + 4);
        const y = centerY + wave;

        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Layer 3: Amber Ochre Fine Accent Wave
      ctx.beginPath();
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = '#B86B0E';
      ctx.shadowBlur = 8;
      ctx.shadowColor = 'rgba(184, 107, 14, 0.55)';

      for (let x = 0; x < width; x += 5) {
        const index = Math.floor((x / width) * 40);
        const amp = (values[index] || 10) / 255;
        const wave = Math.sin(x * 0.03 + time * 1.2) * (amp * 22 + 3);
        const y = centerY + wave;

        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Reset shadow for performance
      ctx.shadowBlur = 0;
    };

    draw();
  }
}

export const audioEngine = new AudioEngine();

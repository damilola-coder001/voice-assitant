/**
 * WebSocket Voice Client with Streaming Binary Audio, State Tracking, Heartbeat, and Interrupt Signals
 */

import { audioEngine } from './audio.js';

export const ConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
  ERROR: 'error',
};

class VoiceWebSocketClient {
  constructor() {
    this.ws = null;
    this.token = null;
    this.state = ConnectionState.DISCONNECTED;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    this.heartbeatTimeout = null;
    this.isManualDisconnect = false;
    this.useHttpFallback = false;
    this.hasOpenedOnce = false;
    this.httpTurnAbortController = null;

    // Callbacks
    this.onStateChange = null;
    this.onReady = null;
    this.onTurnStart = null;
    this.onTextResponse = null;
    this.onTurnComplete = null;
    this.onInterrupted = null;
    this.onError = null;
    this.onClose = null;
    this.onTechIntent = null;
    this.onTechSources = null;
    this.onFactCheckResult = null;
    this.onBriefingData = null;
    this.onVoiceStreamFallback = null;

    this.bindWindowEvents();
  }

  setState(newState, detail = null) {
    if (this.state === newState && newState !== ConnectionState.RECONNECTING) return;
    this.state = newState;
    this.isConnected = (newState === ConnectionState.CONNECTED);
    if (this.onStateChange) {
      this.onStateChange(newState, detail);
    }
  }

  bindWindowEvents() {
    // When tab becomes visible again, check connection health
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        const token = localStorage.getItem('access_token') || this.token;
        if (token && !this.isManualDisconnect && (!this.ws || this.ws.readyState === WebSocket.CLOSED)) {
          console.log('[WebSocket] Tab became visible, verifying voice stream connection...');
          this.reconnectAttempts = 0;
          this.connect(token);
        }
      }
    });

    // Handle network offline/online
    window.addEventListener('online', () => {
      console.log('[WebSocket] Network restored. Re-establishing voice stream...');
      const token = localStorage.getItem('access_token') || this.token;
      if (token && !this.isManualDisconnect) {
        this.reconnectAttempts = 0;
        this.connect(token);
      }
    });

    window.addEventListener('offline', () => {
      console.warn('[WebSocket] Network offline.');
      this.stopHeartbeat();
      this.setState(ConnectionState.DISCONNECTED, 'Network offline');
    });
  }

  connect(token) {
    if (!token || token === 'null' || token === 'undefined') {
      console.warn('[WebSocket] Cannot connect: Valid authentication token is required.');
      this.setState(ConnectionState.DISCONNECTED, 'Authentication required');
      return;
    }

    this.token = token;
    this.isManualDisconnect = false;

    const customWs = localStorage.getItem('nore_ws_url') || window.NORE_WS_URL;
    const isServerlessHost = window.location.hostname.endsWith('.vercel.app') && !customWs;
    if (isServerlessHost || this.useHttpFallback) {
      this.useHttpFallback = true;
      this.setState(ConnectionState.CONNECTED, 'HTTPS Serverless Voice Mode');
      if (this.onReady) {
        this.onReady({ type: 'ready', mode: 'http_fallback' });
      }
      return;
    }

    // Prevent duplicate connections if already open or connecting
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.setState(ConnectionState.CONNECTED);
      }
      return;
    }

    this.cleanupSocket();

    const isReconnecting = this.reconnectAttempts > 0;
    this.setState(
      isReconnecting ? ConnectionState.RECONNECTING : ConnectionState.CONNECTING,
      { attempt: this.reconnectAttempts + 1, maxAttempts: this.maxReconnectAttempts }
    );

    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const customWs = localStorage.getItem('nore_ws_url') || window.NORE_WS_URL;
      const baseWs = customWs ? customWs.replace(/\/+$/, '') : `${protocol}//${window.location.host}`;
      const wsUrl = `${baseWs}/ws/voice?token=${encodeURIComponent(token)}`;

      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        this.hasOpenedOnce = true;
        this.useHttpFallback = false;
        this.reconnectAttempts = 0;
        clearTimeout(this.reconnectTimer);
        this.setState(ConnectionState.CONNECTED);
        this.startHeartbeat();
        console.log('[WebSocket] Voice connection established.');
      };

      this.ws.onmessage = async (event) => {
        // Binary frame = raw audio chunk from ElevenLabs
        if (event.data instanceof ArrayBuffer) {
          await audioEngine.queueAudioChunk(event.data);
          return;
        }

        // JSON control frame
        try {
          const msg = JSON.parse(event.data);
          this.handleJsonMessage(msg);
        } catch (err) {
          console.error('[WebSocket] Error parsing JSON message:', err);
        }
      };

      this.ws.onclose = (event) => {
        this.stopHeartbeat();
        console.log(`[WebSocket] Disconnected (code: ${event.code}, reason: ${event.reason || 'None'})`);

        if (this.onClose) this.onClose(event);

        if (this.isManualDisconnect || event.code === 1000) {
          this.setState(ConnectionState.DISCONNECTED, 'Session closed normally');
          return;
        }

        // Check for policy violation (code 1008) like invalid/expired token
        if (event.code === 1008) {
          console.warn('[WebSocket] Policy violation on connect (auth or session limit):', event.reason);
          this.setState(ConnectionState.ERROR, event.reason || 'Authentication failed or session limit reached.');
          if (this.onError) {
            this.onError(event.reason || 'Session expired or connection limit reached. Please sign in again.');
          }
          return;
        }

        // Auto-reconnect with exponential backoff if below max attempts
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = Math.min(8000, 1200 * Math.pow(1.5, this.reconnectAttempts - 1));
          this.setState(ConnectionState.RECONNECTING, {
            attempt: this.reconnectAttempts,
            maxAttempts: this.maxReconnectAttempts,
            delayMs: delay,
          });

          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = setTimeout(() => {
            const currentToken = localStorage.getItem('access_token') || this.token;
            if (currentToken && currentToken !== 'null' && !this.isManualDisconnect) {
              console.log(`[WebSocket] Reconnecting (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
              this.connect(currentToken);
            } else {
              this.setState(ConnectionState.DISCONNECTED, 'No token available');
            }
          }, delay);
        } else {
          console.warn('[WebSocket] Max reconnect attempts reached; activating HTTPS voice turn fallback.');
          this.useHttpFallback = true;
          this.setState(ConnectionState.CONNECTED, 'HTTPS Serverless Voice Mode');
          if (this.onReady) {
            this.onReady({ type: 'ready', mode: 'http_fallback' });
          }
        }
      };

      this.ws.onerror = (err) => {
        console.warn('[WebSocket] Transport warning or error encountered.');
        // onclose will handle state transition
      };
    } catch (err) {
      console.error('[WebSocket] Setup exception:', err);
      this.setState(ConnectionState.ERROR, err.message);
      if (this.onError) this.onError(err.message);
    }
  }

  startHeartbeat() {
    this.stopHeartbeat();
    // Send ping every 25 seconds to keep proxies/tunnels alive
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
        } catch (_) {}
      }
    }, 25000);
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }

  cleanupSocket() {
    this.stopHeartbeat();
    clearTimeout(this.reconnectTimer);
    if (this.ws) {
      try {
        this.ws.onopen = null;
        this.ws.onclose = null;
        this.ws.onerror = null;
        this.ws.onmessage = null;
        if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
          this.ws.close(1000, "Clean cleanup");
        }
      } catch (_) {}
      this.ws = null;
    }
  }

  handleJsonMessage(msg) {
    switch (msg.type) {
      case 'ready':
        this.setState(ConnectionState.CONNECTED);
        if (this.onReady) this.onReady(msg);
        break;
      case 'pong':
        // Heartbeat acknowledged
        break;
      case 'turn_start':
        if (this.onTurnStart) this.onTurnStart(msg);
        break;
      case 'text_response':
        if (this.onTextResponse) this.onTextResponse(msg.content);
        break;
      case 'audio_stream_start':
        audioEngine.startStreamingPlayback(msg.sample_rate || 24000, msg.channels || 1);
        break;
      case 'audio_stream_end':
        audioEngine.endStreamingPlayback();
        break;
      case 'turn_complete':
        audioEngine.endStreamingPlayback();
        if (this.onTurnComplete) this.onTurnComplete(msg);
        break;
      case 'interrupted':
        audioEngine.stopPlayback();
        if (this.onInterrupted) this.onInterrupted(msg);
        break;
      case 'tech_intent':
        if (this.onTechIntent) this.onTechIntent(msg);
        break;
      case 'tech_sources':
        if (this.onTechSources) this.onTechSources(msg.sources);
        break;
      case 'fact_check_result':
        if (this.onFactCheckResult) this.onFactCheckResult(msg.fact_check);
        break;
      case 'briefing_data':
        if (this.onBriefingData) this.onBriefingData(msg.briefing);
        break;
      case 'voice_stream_fallback':
        if (this.onVoiceStreamFallback) this.onVoiceStreamFallback(msg);
        break;
      case 'timeout':
        console.warn('[WebSocket] Inactivity timeout received from server.');
        break;
      case 'voice_stream_error':
      case 'error':
        if (this.onError) this.onError(msg.message || msg.error);
        break;
    }
  }

  async waitForConnection(timeoutMs = 4000) {
    if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
      return true;
    }
    return new Promise((resolve) => {
      const start = Date.now();
      const check = setInterval(() => {
        if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
          clearInterval(check);
          resolve(true);
        } else if (Date.now() - start > timeoutMs) {
          clearInterval(check);
          resolve(false);
        }
      }, 100);
    });
  }

  async startTurn(text, sessionId, personaId, voiceId) {
    const token = localStorage.getItem('access_token') || this.token || 'guest_token';

    if (this.useHttpFallback) {
      await this.executeHttpTurn(text, sessionId, personaId, voiceId, token);
      return;
    }

    if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.connect(token);
      if (this.useHttpFallback) {
        await this.executeHttpTurn(text, sessionId, personaId, voiceId, token);
        return;
      }
      const ready = await this.waitForConnection(2500);
      if (!ready) {
        console.info('[WebSocket] Falling back to HTTPS voice turn endpoint.');
        this.useHttpFallback = true;
        this.setState(ConnectionState.CONNECTED, 'HTTPS Serverless Voice Mode');
        await this.executeHttpTurn(text, sessionId, personaId, voiceId, token);
        return;
      }
    }

    this.ws.send(JSON.stringify({
      type: 'start_turn',
      text: text,
      session_id: sessionId,
      persona_id: personaId,
      voice_id: voiceId,
    }));
  }

  async executeHttpTurn(text, sessionId, personaId, voiceId, token) {
    if (this.httpTurnAbortController) {
      try {
        this.httpTurnAbortController.abort();
      } catch (_) {}
    }
    this.httpTurnAbortController = new AbortController();

    if (this.onTurnStart) {
      this.onTurnStart({ type: 'turn_start', session_id: sessionId });
    }

    const res = await fetch('/api/speech/turn', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        text: text,
        session_id: sessionId,
        persona_id: personaId || 'executive',
        voice_id: voiceId || null,
      }),
      signal: this.httpTurnAbortController.signal,
    });

    let response = res;
    if (response.status === 401) {
      console.warn('[VoiceClient] Turn rejected (401). Auto-refreshing guest session...');
      try {
        const guestRes = await fetch('/api/auth/guest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        if (guestRes.ok) {
          const guestData = await guestRes.json();
          if (guestData && guestData.access_token) {
            localStorage.setItem('access_token', guestData.access_token);
            if (guestData.refresh_token) localStorage.setItem('refresh_token', guestData.refresh_token);
            response = await fetch('/api/speech/turn', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${guestData.access_token}`,
              },
              body: JSON.stringify({
                text: text,
                session_id: sessionId,
                persona_id: personaId || 'executive',
                voice_id: voiceId || null,
              }),
              signal: this.httpTurnAbortController.signal,
            });
          }
        }
      } catch (e) {
        console.warn('Auto-guest retry error:', e);
      }
    }

    if (!response.ok) {
      let detail = `Voice turn failed (${response.status})`;
      try {
        const errJson = await response.json();
        if (errJson.detail) detail = errJson.detail;
      } catch (_) {}
      throw new Error(detail);
    }

    const data = await response.json();

    if (data.tech_intent && this.onTechIntent) {
      this.onTechIntent(data.tech_intent);
    }
    if (data.tech_sources && this.onTechSources) {
      this.onTechSources(data.tech_sources);
    }
    if (data.fact_check && this.onFactCheckResult) {
      this.onFactCheckResult(data.fact_check);
    }
    if (data.briefing && this.onBriefingData) {
      this.onBriefingData(data.briefing);
    }
    if (data.text_response && this.onTextResponse) {
      this.onTextResponse(data.text_response);
    }

    if (data.audio_base64) {
      const binaryStr = atob(data.audio_base64);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      audioEngine.startStreamingPlayback(data.sample_rate || 24000, data.channels || 1);
      await audioEngine.queueAudioChunk(bytes.buffer);
      audioEngine.endStreamingPlayback();
    } else if (data.fallback === 'browser_speech' && this.onVoiceStreamFallback) {
      this.onVoiceStreamFallback({
        type: 'voice_stream_fallback',
        reason: data.fallback_reason || 'no_api_key',
        message: data.fallback_message || 'Using browser voice synthesis.',
        text: data.text_response,
        message_id: data.message_id,
        session_id: data.session_id,
      });
    }

    if (this.onTurnComplete) {
      this.onTurnComplete({
        type: 'turn_complete',
        session_id: data.session_id,
        message_id: data.message_id,
        latency_ms: data.latency_ms,
        characters: data.characters,
        fallback: data.fallback,
      });
    }
  }

  interrupt() {
    audioEngine.stopPlayback();
    if (this.httpTurnAbortController) {
      try {
        this.httpTurnAbortController.abort();
      } catch (_) {}
      this.httpTurnAbortController = null;
    }
    if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({ type: 'interrupt' }));
      } catch (_) {}
    }
  }

  disconnect() {
    this.isManualDisconnect = true;
    this.useHttpFallback = false;
    this.cleanupSocket();
    this.setState(ConnectionState.DISCONNECTED, 'User signed out');
    this.token = null;
  }
}

export const voiceWs = new VoiceWebSocketClient();

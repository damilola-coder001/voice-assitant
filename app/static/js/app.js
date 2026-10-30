/**
 * Main Application Orchestrator
 */

import { api } from './api.js';
import { audioEngine } from './audio.js';
import { voiceWs } from './websocket.js';
import { chatManager } from './chat.js';
import { adminController } from './admin.js';

export const ConversationState = {
  IDLE: 'IDLE',
  STARTING: 'STARTING',
  LISTENING: 'LISTENING',
  PROCESSING: 'PROCESSING',
  THINKING: 'THINKING',
  SPEAKING: 'SPEAKING',
  STOPPING: 'STOPPING',
  ERROR: 'ERROR',
};

class App {
  constructor() {
    this.currentUser = null;
    this.currentPersona = 'executive';
    this.currentVoiceId = 'CwhRBWXzGAHq8TQ4Fs17';
    this.conversationActive = false;
    this.state = ConversationState.IDLE;
    this.isManualStop = false;
    this.isSpeaking = false;
    this.isThinking = false;
    this.recognition = null;
    this.activeBrowserTranscript = '';
  }

  async init() {
    // Attach audio canvas
    const canvas = document.querySelector('#audio-canvas');
    if (canvas) audioEngine.attachCanvas(canvas);

    // Load persisted interruption mode preference
    const savedBargeInMode = localStorage.getItem('nore_barge_in_mode') || 'voice';
    audioEngine.setBargeInMode(savedBargeInMode);

    this.bindEvents();

    // Check existing auth or auto-login as guest for seamless testing
    const token = api.getAccessToken();
    if (token) {
      try {
        this.currentUser = await api.getMe();
        this.onUserAuthenticated();
      } catch (err) {
        console.warn('Stored session invalid, auto-refreshing guest session:', err);
        await this.autoGuestLogin();
      }
    } else {
      await this.autoGuestLogin();
    }
  }

  async autoGuestLogin() {
    try {
      const authData = await api.loginAsGuest();
      this.currentUser = (authData && authData.user) ? authData.user : { full_name: 'Guest Tester', email: 'guest@nore.ai', role: 'user' };
      this.onUserAuthenticated();
    } catch (err) {
      console.warn('Guest login fallback note:', err);
      this.currentUser = { full_name: 'Guest Tester', email: 'guest@nore.ai', role: 'user' };
      this.onUserAuthenticated();
    }
  }

  bindEvents() {
    // Mobile navigation drawer toggle and close handlers
    const menuToggleBtn = document.querySelector('#btn-menu-toggle');
    const sidebarCloseBtn = document.querySelector('#btn-sidebar-close');
    const sidebarOverlay = document.querySelector('#sidebar-overlay');
    const sidebar = document.querySelector('#sidebar');

    const openSidebar = () => {
      if (sidebar) sidebar.classList.add('open');
      if (sidebarOverlay) sidebarOverlay.classList.add('active');
    };

    const closeSidebar = () => {
      if (sidebar) sidebar.classList.remove('open');
      if (sidebarOverlay) sidebarOverlay.classList.remove('active');
    };

    if (menuToggleBtn) {
      menuToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (sidebar && sidebar.classList.contains('open')) {
          closeSidebar();
        } else {
          openSidebar();
        }
      });
    }

    if (sidebarCloseBtn) {
      sidebarCloseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeSidebar();
      });
    }

    if (sidebarOverlay) {
      sidebarOverlay.addEventListener('click', () => closeSidebar());
    }

    // Close drawer on Escape key
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeSidebar();
      }
    });

    // Close drawer on window resize above tablet
    window.addEventListener('resize', () => {
      if (window.innerWidth > 1024) {
        closeSidebar();
      }
    });

    // User profile card opens settings on click
    const userProfileCard = document.querySelector('.user-profile-card');
    if (userProfileCard) {
      userProfileCard.style.cursor = 'pointer';
      userProfileCard.addEventListener('click', () => {
        closeSidebar();
        this.switchView('settings');
      });
    }

    // Tab switching (closes mobile drawer automatically on select)
    document.querySelectorAll('.nav-item').forEach((item) => {
      item.addEventListener('click', () => {
        closeSidebar();
        const viewId = item.getAttribute('data-view');
        this.switchView(viewId);
      });
    });

    // Start / Stop Continuous Conversation Button
    const sessionBtn = document.querySelector('#btn-session-toggle') || document.querySelector('#btn-mic-main');
    if (sessionBtn) {
      sessionBtn.addEventListener('click', () => this.toggleConversationSession());
    }

    // Clicking the central visualizer orb also toggles the session
    const statusOrb = document.querySelector('#status-orb');
    if (statusOrb) {
      statusOrb.style.cursor = 'pointer';
      statusOrb.title = 'Click to Start / Stop Voice Conversation';
      statusOrb.addEventListener('click', () => this.toggleConversationSession());
    }

    // Spacebar hotkey toggles continuous conversation session
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        this.toggleConversationSession();
      }
    });

    // Interrupt button
    const interruptBtn = document.querySelector('#btn-interrupt');
    if (interruptBtn) {
      interruptBtn.addEventListener('click', () => this.handleBargeIn());
    }

    // Text fallback input
    const textForm = document.querySelector('#form-text-input');
    if (textForm) {
      textForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.querySelector('#input-text-prompt');
        const text = input.value.trim();
        if (text) {
          input.value = '';
          await this.submitVoiceTurn(text);
        }
      });
    }

    // Modal closes
    document.querySelectorAll('.modal-close').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.target.closest('.modal-overlay').classList.remove('active');
      });
    });

    // Auth forms
    this.bindAuthForms();
    this.bindPasswordToggles();

    // Technology Intelligence Quick Action Bar
    document.querySelectorAll('.tech-chip-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const query = btn.getAttribute('data-query');
        if (query) {
          const input = document.querySelector('#input-text-prompt');
          if (input) input.value = query;
          await this.submitVoiceTurn(query);
        }
      });
    });

    // Playback completion hook from audio.js (Auto-return to LISTENING)
    audioEngine.onPlaybackEnd = () => {
      this.isSpeaking = false;
      const interruptBtn = document.querySelector('#btn-interrupt');
      if (interruptBtn) interruptBtn.classList.remove('visible');

      if (this.conversationActive) {
        console.log('[App] Audio playback finished. Automatically returning to LISTENING.');
        this.setConversationState(ConversationState.LISTENING);
        audioEngine.resumeVad();
        audioEngine.playChime('listening');
        this.activeBrowserTranscript = '';
        const ticker = document.querySelector('#transcript-ticker');
        if (ticker) {
          ticker.innerHTML = '<span style="color: var(--status-listening-glow); font-weight: 500;">● Listening... Speak whenever you\'re ready</span>';
        }
      } else {
        this.setConversationState(ConversationState.IDLE);
      }
    };

    // Wire connection state listener from websocket.js
    voiceWs.onStateChange = (state, detail) => {
      if (this.conversationActive) {
        if (state === 'reconnecting') {
          const attemptText = (detail && detail.attempt) ? `RECONNECTING (${detail.attempt}/${detail.maxAttempts})` : 'RECONNECTING';
          this.setConversationState('RECONNECTING', attemptText);
        } else if (state === 'connected') {
          this.setConversationState(ConversationState.LISTENING);
          audioEngine.resumeVad();
        } else if (state === 'error' || state === 'disconnected') {
          if (!this.isManualStop) {
            this.setConversationState('RECONNECTING', 'Reconnecting...');
          }
        }
        return;
      }

      switch (state) {
        case 'connecting':
          this.updateStatus('CONNECTING', 'connecting');
          break;
        case 'connected':
          this.updateStatus('READY', 'idle');
          break;
        case 'reconnecting':
          const attemptText = (detail && detail.attempt) ? `RECONNECTING (${detail.attempt}/${detail.maxAttempts})` : 'RECONNECTING';
          this.updateStatus(attemptText, 'reconnecting');
          break;
        case 'disconnected':
          const token = api.getAccessToken();
          this.updateStatus(token ? 'READY' : 'OFFLINE', 'offline');
          break;
        case 'error':
          this.updateStatus('ERROR', 'error');
          break;
      }
    };

    // WebSocket callbacks: READY, THINKING, SPEAKING, ERROR, OFFLINE
    voiceWs.onReady = () => {
      if (this.conversationActive) {
        this.setConversationState(ConversationState.LISTENING);
        audioEngine.resumeVad();
      } else {
        this.updateStatus('READY', 'idle');
      }
    };
    voiceWs.onTurnStart = (msg) => {
      this.isThinking = true;
      if (msg && msg.session_id) {
        chatManager.currentSessionId = msg.session_id;
      }
      this.setConversationState(ConversationState.THINKING);
      const interruptBtn = document.querySelector('#btn-interrupt');
      if (interruptBtn) interruptBtn.classList.add('visible');
      this.clearTechSlots();
    };
    voiceWs.onTechIntent = (data) => {
      if (data && data.requires_search) {
        this.updateStatus(`RESEARCHING (${(data.domain || 'TECH').toUpperCase()})`, 'thinking');
      }
    };
    voiceWs.onTechSources = (sources) => {
      this.renderTechSources(sources);
    };
    voiceWs.onFactCheckResult = (factCheck) => {
      this.renderFactCheck(factCheck);
    };
    voiceWs.onBriefingData = (briefing) => {
      this.renderBriefing(briefing);
    };
    voiceWs.onTextResponse = (text) => {
      this.isThinking = false;
      this.isSpeaking = true;
      const ticker = document.querySelector('#transcript-ticker');
      if (ticker) {
        ticker.innerHTML = `<strong>Assistant:</strong> ${text}`;
      }
      this.setConversationState(ConversationState.SPEAKING);
    };
    voiceWs.onTurnComplete = () => {
      this.isThinking = false;
      chatManager.loadSessions();
    };
    voiceWs.onVoiceStreamFallback = (data) => {
      console.log('[App] Voice stream fallback to browser speech synthesis:', data.reason);
      if (data.reason === 'quota_exceeded') {
        this.showToast('ElevenLabs voice quota exhausted — speaking with browser voice instead.', 'info');
      } else {
        this.showToast('Neural voice unavailable — speaking with browser voice instead.', 'info');
      }
      this.isSpeaking = true;
      this.setConversationState(ConversationState.SPEAKING);
      audioEngine.speakTextWithBrowser(
        data.text,
        () => {
          this.isSpeaking = true;
          this.setConversationState(ConversationState.SPEAKING);
        },
        () => {
          this.isSpeaking = false;
          if (this.conversationActive) {
            this.setConversationState(ConversationState.LISTENING);
            audioEngine.resumeVad();
          } else {
            this.setConversationState(ConversationState.IDLE);
          }
        }
      );
    };
    voiceWs.onInterrupted = () => {
      this.isThinking = false;
      this.isSpeaking = false;
      if (this.conversationActive) {
        this.setConversationState(ConversationState.LISTENING);
        audioEngine.resumeVad();
        const ticker = document.querySelector('#transcript-ticker');
        if (ticker) {
          ticker.innerHTML = '<span style="color: var(--status-listening-glow); font-weight: 500;">● Interrupted. Listening to you...</span>';
        }
      } else {
        this.setConversationState(ConversationState.IDLE);
      }
      const interruptBtn = document.querySelector('#btn-interrupt');
      if (interruptBtn) interruptBtn.classList.remove('visible');
    };
    voiceWs.onError = (msg) => {
      this.isThinking = false;
      this.isSpeaking = false;
      this.showToast(msg, 'error');
      if (this.conversationActive) {
        this.setConversationState(ConversationState.LISTENING);
        audioEngine.resumeVad();
      } else {
        this.setConversationState(ConversationState.ERROR);
      }
      const interruptBtn = document.querySelector('#btn-interrupt');
      if (interruptBtn) interruptBtn.classList.remove('visible');
    };
  }

  switchView(viewId) {
    document.querySelectorAll('.nav-item').forEach((i) => i.classList.remove('active'));
    document.querySelectorAll('.view-container').forEach((v) => v.classList.remove('active'));

    const navItem = document.querySelector(`.nav-item[data-view="${viewId}"]`);
    const view = document.querySelector(`#view-${viewId}`);

    if (navItem) navItem.classList.add('active');
    if (view) view.classList.add('active');

    if (viewId === 'conversations') {
      chatManager.loadSessions();
    } else if (viewId === 'admin') {
      adminController.init();
    } else if (viewId === 'personas') {
      this.loadPersonasView();
    } else if (viewId === 'studio') {
      const token = api.getAccessToken();
      if (token && !voiceWs.isConnected) {
        voiceWs.connect(token);
      }
    }
  }

  async toggleConversationSession() {
    if (!this.conversationActive) {
      await this.startConversationSession();
    } else {
      await this.stopConversationSession();
    }
  }

  // Alias for backward compatibility if invoked from legacy components
  async toggleRecording() {
    await this.toggleConversationSession();
  }

  async startConversationSession() {
    if (!api.getAccessToken()) {
      await this.autoGuestLogin();
    }

    if (this.conversationActive) return;

    this.isManualStop = false;
    this.conversationActive = true;
    this.setConversationState(ConversationState.STARTING, 'Starting session...');

    // If assistant was playing previous audio, stop it
    audioEngine.stopPlayback(false);

    const ticker = document.querySelector('#transcript-ticker');
    if (ticker) {
      ticker.innerHTML = '<span style="color: var(--gold-bright);">● Starting continuous voice session...</span>';
    }

    // Connect WebSocket if not connected
    if (!voiceWs.isConnected) {
      voiceWs.connect(api.getAccessToken());
    }

    // Browser SpeechRecognition for real-time live captions
    this.activeBrowserTranscript = '';
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      try {
        if (this.recognition) {
          try { this.recognition.stop(); } catch (_) {}
        }
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = 'en-US';
        this.recognition.onresult = (event) => {
          let fullText = '';
          for (let i = 0; i < event.results.length; i++) {
            fullText += event.results[i][0].transcript;
          }
          this.activeBrowserTranscript = fullText.trim();
          if (this.state === ConversationState.LISTENING && this.activeBrowserTranscript) {
            const liveTicker = document.querySelector('#transcript-ticker');
            if (liveTicker) {
              liveTicker.innerHTML = `<strong>You:</strong> ${this.activeBrowserTranscript}`;
            }
          }
        };
        this.recognition.onerror = (e) => {
          console.debug('Browser speech recognition notice:', e.error);
        };
        this.recognition.start();
      } catch (e) {
        console.debug('SpeechRecognition notice:', e);
      }
    }

    // Start continuous microphone capture with VAD
    try {
      await audioEngine.startContinuousListening({
        onSpeechStart: () => {
          if (this.state === ConversationState.LISTENING) {
            this.setConversationState(ConversationState.LISTENING, 'Hearing speech...');
          }
        },
        onSpeechEnd: async (wavBlob) => {
          await this.handleUserSpeechEnd(wavBlob);
        },
        onBargeIn: () => {
          this.handleBargeIn();
        },
        silenceTimeoutMs: 1000,
        minSpeechDurationMs: 350,
      });

      this.setConversationState(ConversationState.LISTENING);
      audioEngine.playChime('start');
      if (ticker) {
        ticker.innerHTML = '<span style="color: var(--status-listening-glow); font-weight: 500;">● Listening... Speak naturally, NORE is listening.</span>';
      }
    } catch (err) {
      console.error('Failed to start continuous voice listening:', err);
      this.conversationActive = false;
      this.showToast(err.message, 'error');
      this.setConversationState(ConversationState.ERROR, err.message);
      if (this.recognition) {
        try { this.recognition.stop(); } catch (_) {}
      }
    }
  }

  async stopConversationSession() {
    this.isManualStop = true;
    this.conversationActive = false;
    this.setConversationState(ConversationState.STOPPING, 'Stopping session...');

    // 1. Stop continuous microphone & VAD
    audioEngine.stopContinuousListening();

    // 2. Stop browser speech recognition
    if (this.recognition) {
      try { this.recognition.stop(); } catch (_) {}
      this.recognition = null;
    }

    // 3. Stop audio playback and flush queue
    audioEngine.stopPlayback(true);

    // 4. Cancel in-flight voice synthesis
    voiceWs.interrupt();

    // 5. Update state to IDLE
    this.isSpeaking = false;
    this.isThinking = false;
    this.setConversationState(ConversationState.IDLE);

    const ticker = document.querySelector('#transcript-ticker');
    if (ticker) {
      ticker.innerHTML = '<div class="transcript-placeholder">Click <strong>Start Conversation</strong> or press <strong>Spacebar</strong> to begin.</div>';
    }

    const interruptBtn = document.querySelector('#btn-interrupt');
    if (interruptBtn) interruptBtn.classList.remove('visible');

    // 6. Reload conversations vault to preserve session
    chatManager.loadSessions();
  }

  async handleUserSpeechEnd(wavBlob) {
    if (!this.conversationActive || this.state !== ConversationState.LISTENING) {
      return;
    }

    // Temporarily pause VAD while processing
    audioEngine.pauseVad();

    const ticker = document.querySelector('#transcript-ticker');
    let recognizedText = '';

    // 1. Instant client-side speech transcript if available (0ms network delay)
    if (this.activeBrowserTranscript && this.activeBrowserTranscript.trim().length >= 2) {
      recognizedText = this.activeBrowserTranscript.trim();
    }

    // 2. Server-side ElevenLabs STT fallback if browser transcript is empty
    if (!recognizedText && wavBlob && wavBlob.size > 200) {
      const formData = new FormData();
      formData.append('audio_file', wavBlob, 'mic.wav');
      try {
        const res = await api.request('/speech/stt', {
          method: 'POST',
          body: formData,
        });
        if (res && res.text && res.text.trim()) {
          recognizedText = res.text.trim();
        }
      } catch (err) {
        console.warn('Backend STT notice:', err);
      }
    }

    // Check for empty or bracket noise artifacts like [silence], [cough], [applause]
    if (!recognizedText || /^\[.*?\]$/.test(recognizedText)) {
      if (this.conversationActive) {
        // Return cleanly to listening without annoying the user
        this.setConversationState(ConversationState.LISTENING);
        audioEngine.resumeVad();
        this.activeBrowserTranscript = '';
        if (ticker) {
          ticker.innerHTML = '<span style="color: var(--status-listening-glow); font-weight: 500;">● Listening... Speak whenever you\'re ready</span>';
        }
      }
      return;
    }

    // Valid speech obtained! Transition to THINKING and submit to AI
    this.activeBrowserTranscript = '';
    this.isThinking = true;
    this.setConversationState(ConversationState.THINKING);
    await this.submitVoiceTurn(recognizedText);
  }

  handleBargeIn() {
    console.log('[App] Barge-In initiated: stopping playback and returning to listening.');
    audioEngine.playChime('interrupt');
    voiceWs.interrupt();
    audioEngine.stopPlayback(true);
    this.isSpeaking = false;

    const interruptBtn = document.querySelector('#btn-interrupt');
    if (interruptBtn) interruptBtn.classList.remove('visible');

    if (this.conversationActive) {
      this.setConversationState(ConversationState.LISTENING, 'Interrupted');
      audioEngine.resumeVad();
      this.activeBrowserTranscript = '';
      const ticker = document.querySelector('#transcript-ticker');
      if (ticker) {
        ticker.innerHTML = '<span style="color: var(--status-listening-glow); font-weight: 500;">● Interrupted assistant. Listening to your question...</span>';
      }
    } else {
      this.setConversationState(ConversationState.IDLE);
    }
  }

  async submitVoiceTurn(text) {
    const ticker = document.querySelector('#transcript-ticker');
    if (ticker) {
      ticker.innerHTML = `<strong>You:</strong> ${text}`;
    }

    try {
      await voiceWs.startTurn(
        text,
        chatManager.currentSessionId,
        this.currentPersona,
        this.currentVoiceId,
      );
    } catch (err) {
      this.showToast(err.message, 'error');
      if (this.conversationActive) {
        this.setConversationState(ConversationState.LISTENING);
        audioEngine.resumeVad();
      } else {
        this.setConversationState(ConversationState.IDLE);
      }
    }
  }

  updateSessionButtonUI(active) {
    const btn = document.querySelector('#btn-session-toggle') || document.querySelector('#btn-mic-main');
    if (!btn) return;

    if (active) {
      btn.className = 'btn-conversation-toggle active';
      btn.setAttribute('aria-pressed', 'true');
      btn.title = 'Stop Voice Conversation (Spacebar)';
      btn.innerHTML = `
        <div class="btn-icon-wrapper" id="btn-session-icon">
          <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect>
          </svg>
        </div>
        <span id="btn-session-label">STOP CONVERSATION</span>
      `;
    } else {
      btn.className = 'btn-conversation-toggle idle';
      btn.setAttribute('aria-pressed', 'false');
      btn.title = 'Start Voice Conversation (Spacebar)';
      btn.innerHTML = `
        <div class="btn-icon-wrapper" id="btn-session-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" fill="none" stroke-width="2.2">
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
            <line x1="12" y1="19" x2="12" y2="22"></line>
          </svg>
        </div>
        <span id="btn-session-label">START CONVERSATION</span>
      `;
    }
  }

  setConversationState(state, customLabel = null) {
    this.state = state;

    let orbClass = 'idle';
    if (state === ConversationState.LISTENING) orbClass = 'listening';
    else if (state === ConversationState.PROCESSING) orbClass = 'processing';
    else if (state === ConversationState.THINKING) orbClass = 'thinking';
    else if (state === ConversationState.SPEAKING) orbClass = 'speaking';
    else if (state === ConversationState.STARTING || state === 'CONNECTING') orbClass = 'connecting';
    else if (state === 'RECONNECTING') orbClass = 'reconnecting';
    else if (state === ConversationState.ERROR) orbClass = 'error';

    const pill = document.querySelector('#status-pill-text');
    if (pill) {
      if (this.conversationActive) {
        pill.textContent = 'CONVERSATION ACTIVE';
      } else {
        pill.textContent = 'Voice Ready';
      }
    }

    const orb = document.querySelector('#status-orb');
    if (orb) {
      orb.className = 'status-orb ' + orbClass;
    }

    const stateLabel = document.querySelector('#status-text-label');
    if (stateLabel) {
      stateLabel.textContent = (customLabel || state).toUpperCase();
    }

    const dot = document.querySelector('#status-dot');
    if (dot) {
      dot.className = 'status-dot ' + orbClass;
    }

    this.updateSessionButtonUI(this.conversationActive);
  }

  updateStatus(label, orbState) {
    this.setConversationState(this.state || ConversationState.IDLE, label);
  }

  showToast(message, type = 'info') {
    const container = document.querySelector('#toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- Auth Dialog & User Setup ---
  showAuthModal() {
    const modal = document.querySelector('#modal-auth');
    if (modal) modal.classList.add('active');
  }

  hideAuthModal() {
    const modal = document.querySelector('#modal-auth');
    if (modal) modal.classList.remove('active');
  }

  bindAuthForms() {
    const loginForm = document.querySelector('#form-login');
    if (loginForm) {
      loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.querySelector('#login-email').value;
        const password = document.querySelector('#login-password').value;
        try {
          await api.login(email, password);
          this.currentUser = await api.getMe();
          this.hideAuthModal();
          this.onUserAuthenticated();
          this.showToast('Welcome back!', 'success');
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }
    // Toggle to register form
    const toggleToReg = document.querySelector('#toggle-to-register');
    if (toggleToReg) {
      toggleToReg.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelector('#auth-login-section').style.display = 'none';
        document.querySelector('#auth-reset-section').style.display = 'none';
        document.querySelector('#auth-register-section').style.display = 'block';
      });
    }

    const toggleToLog = document.querySelector('#toggle-to-login');
    if (toggleToLog) {
      toggleToLog.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelector('#auth-register-section').style.display = 'none';
        document.querySelector('#auth-reset-section').style.display = 'none';
        document.querySelector('#auth-login-section').style.display = 'block';
      });
    }

    // Toggle to password reset form
    const toggleToReset = document.querySelector('#toggle-to-reset');
    if (toggleToReset) {
      toggleToReset.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelector('#auth-login-section').style.display = 'none';
        document.querySelector('#auth-register-section').style.display = 'none';
        document.querySelector('#auth-reset-section').style.display = 'block';
        const confirmForm = document.querySelector('#form-reset-confirm');
        if (confirmForm) confirmForm.style.display = 'none';
      });
    }

    const toggleResetToLog = document.querySelector('#toggle-reset-to-login');
    if (toggleResetToLog) {
      toggleResetToLog.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelector('#auth-reset-section').style.display = 'none';
        document.querySelector('#auth-register-section').style.display = 'none';
        document.querySelector('#auth-login-section').style.display = 'block';
      });
    }

    // Password reset request form
    const resetReqForm = document.querySelector('#form-reset-request');
    if (resetReqForm) {
      resetReqForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.querySelector('#reset-req-email').value.trim();
        try {
          const res = await api.requestPasswordReset(email);
          this.showToast(res.message || 'Recovery instructions sent.', 'success');
          const confirmForm = document.querySelector('#form-reset-confirm');
          if (confirmForm) {
            confirmForm.style.display = 'block';
            if (res.debug_reset_token) {
              const tokenInput = document.querySelector('#reset-confirm-token');
              if (tokenInput) tokenInput.value = res.debug_reset_token;
            }
          }
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }

    // Password reset confirm form
    const resetConfirmForm = document.querySelector('#form-reset-confirm');
    if (resetConfirmForm) {
      resetConfirmForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const token = document.querySelector('#reset-confirm-token').value.trim();
        const newPassword = document.querySelector('#reset-confirm-password').value;
        try {
          const res = await api.confirmPasswordReset(token, newPassword);
          this.showToast(res.message || 'Password reset successfully! Please log in.', 'success');
          document.querySelector('#auth-reset-section').style.display = 'none';
          document.querySelector('#auth-login-section').style.display = 'block';
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }

    const regForm = document.querySelector('#form-register');
    if (regForm) {
      regForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.querySelector('#reg-email').value;
        const password = document.querySelector('#reg-password').value;
        const name = document.querySelector('#reg-name').value;
        try {
          await api.register(email, password, name);
          this.currentUser = await api.getMe();
          this.hideAuthModal();
          this.onUserAuthenticated();
          this.showToast('Account created successfully!', 'success');
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }

    // Logout
    const logoutBtn = document.querySelector('#btn-logout');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', async () => {
        await api.logout();
        voiceWs.disconnect();
        window.location.reload();
      });
    }
  }

  bindPasswordToggles() {
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-password-toggle');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();

      const targetId = btn.getAttribute('data-target');
      const input = (targetId ? document.getElementById(targetId) : null) || btn.parentElement.querySelector('input');
      if (!input) return;

      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      btn.classList.toggle('showing', isPassword);
      const newLabel = isPassword ? 'Hide password' : 'Show password';
      btn.setAttribute('aria-label', newLabel);
      btn.setAttribute('title', newLabel);
      input.focus();
    });
  }

  onUserAuthenticated() {
    // Show user in sidebar
    document.querySelector('#sidebar-user-name').textContent = this.currentUser.full_name || this.currentUser.email;
    const roleEl = document.querySelector('#sidebar-user-role');
    if (roleEl) {
      // In dormant RBAC mode: keep role badges hidden from interface
      roleEl.style.display = 'none';
    }

    // In dormant RBAC mode: keep Admin dashboard hidden from navigation
    const adminNav = document.querySelector('.nav-item[data-view="admin"]');
    if (adminNav) {
      adminNav.style.display = 'none';
    }

    // Connect WebSocket
    const token = api.getAccessToken();
    voiceWs.connect(token);

    // Load initial voice preference
    if (this.currentUser.voice_preference) {
      this.currentVoiceId = this.currentUser.voice_preference.preferred_voice_id || 'CwhRBWXzGAHq8TQ4Fs17';
      this.currentPersona = this.currentUser.voice_preference.active_persona_id || 'executive';
    }
  }

  async loadPersonasView() {
    const personasContainer = document.querySelector('#personas-catalog');
    if (!personasContainer) return;

    try {
      const personas = await api.getPersonas();
      personasContainer.innerHTML = personas
        .map((p) => {
          const isSelected = p.id === this.currentPersona;
          return `
            <div class="glass-card persona-card ${isSelected ? 'selected' : ''}" data-id="${p.id}" style="
              border-color: ${isSelected ? 'var(--gold-bright)' : 'var(--border-glass)'};
              box-shadow: ${isSelected ? '0 0 25px var(--gold-glow), var(--inner-bevel)' : 'var(--shadow-luxe)'};
              cursor: pointer;
              transition: all var(--transition-normal);
            ">
              <div style="font-size: 1rem; color: var(--gold-bright); font-weight: 700; letter-spacing: 0.05em; margin-bottom: 0.5rem;">${p.name.toUpperCase()}</div>
              <h3 style="font-family: var(--font-heading); margin-bottom: 0.25rem; color: #FFFFFF;">${p.name}</h3>
              <p style="font-size: 0.82rem; color: var(--gold-bright); margin-bottom: 0.5rem; font-weight: 600;">${p.tagline}</p>
              <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">${p.description}</p>
              <button class="btn ${isSelected ? 'btn-primary' : 'btn-secondary'} btn-select-persona" data-id="${p.id}" style="margin-top: 1.25rem; width: 100%;">
                ${isSelected ? 'Active Persona' : 'Select Persona'}
              </button>
            </div>
          `;
        })
        .join('');

      personasContainer.querySelectorAll('.btn-select-persona').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const pId = btn.getAttribute('data-id');
          this.currentPersona = pId;
          try {
            await api.updateVoicePreferences({ active_persona_id: pId });
          } catch (_) {}
          this.loadPersonasView();
          this.showToast(`Active persona switched to ${pId}`, 'success');
        });
      });

      // Also load voices
      const voicesList = await api.getVoices();
      const voicesSelect = document.querySelector('#voice-picker-select');
      if (voicesSelect) {
        voicesSelect.innerHTML = voicesList
          .map((v) => `<option value="${v.voice_id}" ${v.voice_id === this.currentVoiceId ? 'selected' : ''}>${v.name} (${v.category})</option>`)
          .join('');
        voicesSelect.onchange = async () => {
          this.currentVoiceId = voicesSelect.value;
          try {
            await api.updateVoicePreferences({ preferred_voice_id: this.currentVoiceId });
            this.showToast('Preferred voice updated.', 'success');
          } catch (_) {}
        };
      }

      // Voice preview sample button
      const btnPreviewVoice = document.querySelector('#btn-preview-voice');
      if (btnPreviewVoice) {
        btnPreviewVoice.onclick = async () => {
          const vSelect = document.querySelector('#voice-picker-select');
          if (!vSelect || !vSelect.value) return;
          const origText = btnPreviewVoice.innerHTML;
          btnPreviewVoice.innerHTML = '⏳ Playing...';
          btnPreviewVoice.disabled = true;
          try {
            const blob = await api.previewVoice(vSelect.value, "Hello! I am NORE, your real-time voice assistant.");
            if (blob && blob.size > 0) {
              await audioEngine.playBlob(blob);
            }
          } catch (err) {
            console.warn('[App] Voice preview fallback to browser speech synthesis:', err);
            audioEngine.speakTextWithBrowser("Hello! I am NORE, your real-time voice assistant.");
            this.showToast('ElevenLabs quota limit reached. Previewing via browser voice.', 'info');
          } finally {
            btnPreviewVoice.innerHTML = origText;
            btnPreviewVoice.disabled = false;
          }
        };
      }

      // Populate personality form inputs
      try {
        const prefs = await api.getVoicePreferences();
        if (prefs) {
          if (document.querySelector('#pref-assistant-name')) document.querySelector('#pref-assistant-name').value = prefs.assistant_name || 'NORE';
          if (document.querySelector('#pref-speed-slider')) {
            document.querySelector('#pref-speed-slider').value = prefs.speed || 1.0;
            document.querySelector('#pref-speed-val').textContent = `${(prefs.speed || 1.0).toFixed(2)}x`;
          }
          if (document.querySelector('#pref-tone-select')) document.querySelector('#pref-tone-select').value = prefs.tone || 'balanced';
          if (document.querySelector('#pref-formality-select')) document.querySelector('#pref-formality-select').value = prefs.formality || 'professional';
          if (document.querySelector('#pref-style-select')) document.querySelector('#pref-style-select').value = prefs.response_style || 'adaptive';
          if (document.querySelector('#pref-lang-select')) document.querySelector('#pref-lang-select').value = prefs.preferred_language || 'en';

          // Tech Intelligence Preferences
          if (prefs.tech_interests) {
            const activeList = prefs.tech_interests.split(',').map((s) => s.trim());
            document.querySelectorAll('#tech-interests-chips .interest-chip').forEach((chip) => {
              const dom = chip.getAttribute('data-domain');
              if (activeList.includes(dom)) {
                chip.classList.add('active');
              } else {
                chip.classList.remove('active');
              }
            });
          }
          if (document.querySelector('#pref-tech-level-select')) {
            document.querySelector('#pref-tech-level-select').value = prefs.tech_explanation_level || 'intermediate';
          }
          if (document.querySelector('#pref-tech-summary-select')) {
            document.querySelector('#pref-tech-summary-select').value = prefs.tech_summary_style || 'balanced';
          }
        }
      } catch (e) {
        console.warn('Could not load detailed voice preferences:', e);
      }

      // Tech interest chip toggle listeners
      document.querySelectorAll('#tech-interests-chips .interest-chip').forEach((chip) => {
        chip.onclick = () => {
          chip.classList.toggle('active');
        };
      });

      // Speed slider live listener
      const speedSlider = document.querySelector('#pref-speed-slider');
      if (speedSlider) {
        speedSlider.oninput = (e) => {
          document.querySelector('#pref-speed-val').textContent = `${parseFloat(e.target.value).toFixed(2)}x`;
        };
      }

      // Interruption mode live listener
      const interruptModeSelect = document.querySelector('#pref-interrupt-mode');
      if (interruptModeSelect) {
        // Restore saved value
        const savedMode = localStorage.getItem('nore_barge_in_mode') || 'voice';
        interruptModeSelect.value = savedMode;

        interruptModeSelect.onchange = () => {
          const mode = interruptModeSelect.value;
          audioEngine.setBargeInMode(mode);
          localStorage.setItem('nore_barge_in_mode', mode);
          this.showToast(
            mode === 'manual'
              ? 'Interruption mode: Tap to Interrupt (button only)'
              : 'Interruption mode: Voice Barge-In (speak to interrupt)',
            'success'
          );
        };
      }

      // Form personality submit listener
      const formPersonality = document.querySelector('#form-personality-settings');
      if (formPersonality) {
        formPersonality.onsubmit = async (e) => {
          e.preventDefault();
          const assistantName = document.querySelector('#pref-assistant-name').value.trim();
          const voiceId = document.querySelector('#voice-picker-select').value;
          const modelId = document.querySelector('#model-picker-select').value;
          const speed = parseFloat(document.querySelector('#pref-speed-slider').value);
          const tone = document.querySelector('#pref-tone-select').value;
          const formality = document.querySelector('#pref-formality-select').value;
          const responseStyle = document.querySelector('#pref-style-select').value;
          const preferredLanguage = document.querySelector('#pref-lang-select').value;

          const activeDomains = Array.from(document.querySelectorAll('#tech-interests-chips .interest-chip.active'))
            .map((c) => c.getAttribute('data-domain'))
            .join(',');
          const techLevel = document.querySelector('#pref-tech-level-select') ? document.querySelector('#pref-tech-level-select').value : 'intermediate';
          const techSummary = document.querySelector('#pref-tech-summary-select') ? document.querySelector('#pref-tech-summary-select').value : 'balanced';

          try {
            await api.updateVoicePreferences({
              preferred_voice_id: voiceId,
              preferred_model_id: modelId,
              assistant_name: assistantName,
              speed: speed,
              tone: tone,
              formality: formality,
              response_style: responseStyle,
              preferred_language: preferredLanguage,
              active_persona_id: this.currentPersona,
              tech_interests: activeDomains || 'ai_ml,software_dev,cybersecurity',
              tech_explanation_level: techLevel,
              tech_summary_style: techSummary,
            });
            this.currentVoiceId = voiceId;
            this.showToast('Assistant personality & technology preferences saved!', 'success');
          } catch (err) {
            this.showToast('Failed to save preferences: ' + err.message, 'error');
          }
        };
      }
    } catch (err) {
      console.error('Error loading personas:', err);
    }
  }

  clearTechSlots() {
    const fcSlot = document.querySelector('#tech-factcheck-slot');
    const bSlot = document.querySelector('#tech-briefing-slot');
    const sSlot = document.querySelector('#tech-sources-slot');
    if (fcSlot) fcSlot.innerHTML = '';
    if (bSlot) bSlot.innerHTML = '';
    if (sSlot) sSlot.innerHTML = '';
  }

  renderTechSources(sources) {
    const sSlot = document.querySelector('#tech-sources-slot');
    if (!sSlot || !sources || sources.length === 0) return;

    const cardsHtml = sources
      .map((s) => {
        const tierBadge = s.is_primary_source
          ? '<span class="source-credibility-tier" style="background: rgba(16,185,129,0.2); color: #34D399;">Primary Source</span>'
          : `<span class="source-credibility-tier">${(s.credibility_tier || 'source').toUpperCase()}</span>`;
        const pubDate = s.published_date ? `<span style="font-size:0.7rem; color: var(--text-muted); margin-left: 0.35rem;">• ${s.published_date}</span>` : '';
        return `
          <a href="${s.url}" target="_blank" rel="noopener noreferrer" class="source-card">
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span class="source-publisher-badge">${s.publisher || 'Verified Web Source'}</span>
              ${tierBadge}
            </div>
            <div class="source-title">${s.title} ${pubDate}</div>
            <div class="source-snippet">${s.snippet || ''}</div>
          </a>
        `;
      })
      .join('');

    sSlot.innerHTML = `
      <div class="tech-sources-panel">
        <div class="tech-sources-header">
          <div class="tech-sources-title">
            <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
            Verified Real-Time Web Sources (${sources.length})
          </div>
        </div>
        <div class="sources-grid">
          ${cardsHtml}
        </div>
      </div>
    `;
  }

  renderFactCheck(factCheck) {
    const fcSlot = document.querySelector('#tech-factcheck-slot');
    if (!fcSlot || !factCheck) return;

    let verdictClass = 'verdict-unverified';
    if (factCheck.verdict === 'CONFIRMED') verdictClass = 'verdict-confirmed';
    else if (factCheck.verdict === 'LIKELY_TRUE') verdictClass = 'verdict-likely';
    else if (factCheck.verdict === 'DISPUTED' || factCheck.verdict === 'FALSE') verdictClass = 'verdict-disputed';

    const confPct = Math.round((factCheck.confidence || 0.5) * 100);

    fcSlot.innerHTML = `
      <div class="factcheck-card">
        <div class="factcheck-header">
          <div style="font-size: 0.84rem; font-weight: 600; color: var(--gold-bright); letter-spacing: 0.04em;">FACT-CHECK VERIFICATION</div>
          <span class="verdict-badge ${verdictClass}">
            ${factCheck.verdict}
          </span>
        </div>
        <div style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.4rem;">
          "${factCheck.claim}"
        </div>
        <div class="confidence-bar-wrapper">
          <span style="font-size: 0.76rem; color: var(--text-secondary); min-width: 90px;">Confidence: ${confPct}%</span>
          <div class="confidence-bar-bg">
            <div class="confidence-bar-fill" style="width: ${confPct}%;"></div>
          </div>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4;">
          ${factCheck.explanation}
        </div>
      </div>
    `;
  }

  renderBriefing(briefing) {
    const bSlot = document.querySelector('#tech-briefing-slot');
    if (!bSlot || !briefing || !briefing.items || briefing.items.length === 0) return;

    const itemsHtml = briefing.items
      .map(
        (item) => `
        <div class="briefing-item-card">
          <div class="briefing-item-header">
            <span>${item.domain_label || item.domain}</span>
            ${item.importance === 'critical' ? '<span style="color: #F87171; margin-left: auto; font-size: 0.7rem; font-weight: 700;">CRITICAL</span>' : ''}
          </div>
          <div class="briefing-item-headline">${item.headline}</div>
          <div class="briefing-item-summary">${item.summary}</div>
        </div>
      `
      )
      .join('');

    bSlot.innerHTML = `
      <div class="briefing-panel">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
          <h4 style="font-family: var(--font-heading); font-size: 1rem; color: var(--gold-bright);">
            Technology Intelligence Digest: ${briefing.briefing_type.toUpperCase()}
          </h4>
          <span style="font-size: 0.74rem; color: var(--text-muted);">
            ${briefing.items.length} updates compiled
          </span>
        </div>
        <div class="briefing-items-grid">
          ${itemsHtml}
        </div>
      </div>
    `;
  }
}

// Instantiate on DOM load
window.addEventListener('DOMContentLoaded', () => {
  const app = new App();
  app.init();
});

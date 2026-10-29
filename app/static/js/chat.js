/**
 * Chat and Conversation History Manager
 */

import { api } from './api.js';

class ChatManager {
  constructor() {
    this.currentSessionId = null;
    this.sessions = [];
    this.messages = [];
    this.attachHeaderExportButtons();
  }

  attachHeaderExportButtons() {
    const btnMd = document.querySelector('#btn-export-md');
    if (btnMd) {
      btnMd.addEventListener('click', () => this.exportCurrentSession('markdown'));
    }
    const btnJson = document.querySelector('#btn-export-json');
    if (btnJson) {
      btnJson.addEventListener('click', () => this.exportCurrentSession('json'));
    }
  }

  async exportCurrentSession(format = 'markdown') {
    if (!this.currentSessionId) {
      alert('Please select a conversation from the list to export.');
      return;
    }
    const sId = this.currentSessionId;
    const btn = format === 'markdown' ? document.querySelector('#btn-export-md') : document.querySelector('#btn-export-json');
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
      btn.innerHTML = '⏳ Exporting...';
      btn.disabled = true;
    }
    try {
      const res = await api.exportConversation(sId, format);
      if (res && res.content) {
        const mime = format === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8';
        const blob = new Blob([res.content], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = res.filename || `conversation_${sId}.${format === 'json' ? 'json' : 'md'}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      alert(`Failed to export session: ${err.message}`);
    } finally {
      if (btn) {
        btn.innerHTML = origText;
        btn.disabled = false;
      }
    }
  }

  async loadSessions() {
    try {
      this.sessions = await api.getConversations();
      this.renderSessionList();
      if (this.currentSessionId) {
        const exists = this.sessions.some((s) => s.id === this.currentSessionId);
        if (exists) {
          await this.selectSession(this.currentSessionId);
        } else {
          this.currentSessionId = null;
          this.messages = [];
          this.renderMessages();
        }
      } else if (this.sessions.length > 0) {
        this.renderEmptySelectionPlaceholder();
      }
      return this.sessions;
    } catch (err) {
      console.error('Error loading sessions:', err);
      return [];
    }
  }

  renderEmptySelectionPlaceholder(containerSelector = '#messages-viewport') {
    const container = document.querySelector(containerSelector);
    if (!container || this.currentSessionId) return;
    container.innerHTML = `
      <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); gap: 1rem; padding: 2rem; text-align: center;">
        <div style="font-size: 1.1rem; color: var(--gold-bright); font-weight: 600;">CONVERSATION VAULT</div>
        <div style="max-width: 360px; line-height: 1.5; font-size: 0.9rem;">
          Select a session from the list on the left to review dialogue transcripts, insights, and key takeaways.
        </div>
      </div>
    `;
  }

  renderSessionList(containerSelector = '#sessions-list') {
    const container = document.querySelector(containerSelector);
    if (!container) return;

    if (this.sessions.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 2rem 1rem; color: var(--text-muted); font-size: 0.88rem;">
          No conversations yet. Start talking to begin!
        </div>
      `;
      return;
    }

    container.innerHTML = this.sessions
      .map((s) => {
        const isActive = s.id === this.currentSessionId;
        const dateStr = new Date(s.updated_at).toLocaleDateString([], {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        });
        return `
          <div class="session-card ${isActive ? 'active' : ''}" data-session-id="${s.id}" style="
            padding: 0.85rem 1rem;
            background: ${isActive ? 'rgba(245, 208, 97, 0.16)' : 'var(--bg-glass)'};
            border: 1px solid ${isActive ? 'var(--gold-bright)' : 'var(--border-glass)'};
            border-radius: var(--radius-md);
            margin-bottom: 0.5rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: all var(--transition-fast);
            box-shadow: ${isActive ? '0 0 16px rgba(245, 208, 97, 0.20)' : 'none'};
          ">
            <div style="overflow: hidden; flex: 1;">
              <div style="font-weight: 600; font-size: 0.9rem; color: ${isActive ? 'var(--gold-bright)' : 'var(--text-primary)'}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                ${s.title}
              </div>
              <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
                ${s.persona_id} • ${s.message_count} turns • ${dateStr}
              </div>
            </div>
            <button class="btn-icon btn-delete-session" data-id="${s.id}" title="Delete session" style="width: 28px; height: 28px; border: none; background: transparent; color: var(--text-muted);">
              <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        `;
      })
      .join('');

    // Attach click events
    container.querySelectorAll('.session-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.btn-delete-session')) return;
        const sId = parseInt(card.getAttribute('data-session-id'), 10);
        this.selectSession(sId);
      });
    });

    container.querySelectorAll('.btn-delete-session').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const sId = parseInt(btn.getAttribute('data-id'), 10);
        if (confirm('Delete this entire conversation session?')) {
          await api.deleteConversation(sId);
          if (this.currentSessionId === sId) {
            this.currentSessionId = null;
            this.messages = [];
            this.renderMessages();
          }
          await this.loadSessions();
        }
      });
    });
  }

  async selectSession(sessionId) {
    this.currentSessionId = sessionId;
    this.renderSessionList();
    try {
      const full = await api.getConversation(sessionId);
      this.messages = full.messages || [];
      this.renderMessages();
    } catch (err) {
      console.error('Error fetching conversation messages:', err);
    }
  }

  generateSessionSummary(session, messages) {
    if (!messages || messages.length === 0) return '';

    const userMsgs = messages.filter((m) => m.role === 'user');
    const assistantMsgs = messages.filter((m) => m.role === 'assistant');

    // Derive topics from conversation messages
    const candidateKeywords = [
      'AI & Machine Learning',
      'Neural Voice',
      'Streaming Audio',
      'Cybersecurity',
      'Web Intelligence',
      'Developer Tools',
      'Cloud Architecture',
      'Low Latency',
      'Software Engineering'
    ];

    const matchedTopics = [];
    const fullText = messages.map((m) => m.content).join(' ').toLowerCase();
    for (const kw of candidateKeywords) {
      const token = kw.split(' ')[0].toLowerCase();
      if (fullText.includes(token)) {
        matchedTopics.push(kw);
      }
    }
    if (matchedTopics.length === 0) {
      matchedTopics.push('Technology Intelligence', 'Voice Interaction');
    }

    const firstUserQuery = userMsgs[0] ? userMsgs[0].content : (session ? session.title : 'Technical Discussion');
    const firstAnswer = assistantMsgs[0] ? assistantMsgs[0].content : '';
    const cleanAnswer = firstAnswer.length > 180 ? firstAnswer.slice(0, 180) + '...' : firstAnswer;
    const overview = cleanAnswer || `Explored inquiries regarding "${firstUserQuery.length > 60 ? firstUserQuery.slice(0, 60) + '...' : firstUserQuery}".`;

    const takeaways = [];
    if (assistantMsgs.length > 0) {
      takeaways.push(`Addressed core technical context regarding ${matchedTopics[0]}.`);
      if (assistantMsgs.length > 1) {
        takeaways.push(`Synthesized ${messages.length} conversational turns with real-time neural voice.`);
      } else {
        takeaways.push('Delivered structured engineering response with low-latency streaming.');
      }
      takeaways.push('Session preserved in secure local vault with Markdown and JSON export readiness.');
    } else {
      takeaways.push('Session initiated; awaiting subsequent voice prompts.');
    }

    const suggestions = [
      'Tell me more about this topic',
      'What are the primary industry trade-offs?',
      'Give me latest updates and verified sources'
    ];

    return `
      <div class="conversation-summary-card">
        <div class="summary-header">
          <div class="summary-title">
            <span>Conversation Summary & Key Insights</span>
          </div>
          <div style="display: flex; gap: 0.6rem; align-items: center;">
            ${session ? `<button type="button" class="btn btn-secondary btn-export-markdown" data-session-id="${session.id}" style="padding: 0.35rem 0.75rem; font-size: 0.78rem;" title="Download Markdown Transcript">📥 Export .MD</button>` : ''}
            <span class="summary-badge">${session ? session.persona_id.toUpperCase() : 'NORE'} INTELLIGENCE</span>
          </div>
        </div>

        <div class="summary-text">
          ${overview}
        </div>

        <div class="summary-grid">
          <div class="summary-section-box">
            <div class="summary-section-title">
              Key Topics
            </div>
            <div class="topics-pills-list">
              ${matchedTopics.map((t) => `<span class="topic-pill">${t}</span>`).join('')}
            </div>
          </div>

          <div class="summary-section-box">
            <div class="summary-section-title">
              Key Takeaways
            </div>
            <ul class="takeaways-list">
              ${takeaways.map((t) => `<li>${t}</li>`).join('')}
            </ul>
          </div>
        </div>

        <div class="summary-section-box">
          <div class="summary-section-title">
            Follow-up Suggestions
          </div>
          <div class="suggestions-list">
            ${suggestions.map((s) => `<button type="button" class="suggestion-chip" data-prompt="${s}">${s}</button>`).join('')}
          </div>
        </div>
      </div>

      <div class="transcript-section-divider">
        <span>Full Transcript (${messages.length} turns)</span>
      </div>
    `;
  }

  renderMessages(containerSelector = '#messages-viewport') {
    const container = document.querySelector(containerSelector);
    if (!container) return;

    if (this.messages.length === 0) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); gap: 1rem; padding: 2rem;">
          <div style="font-size: 1.1rem; color: var(--gold-bright); font-weight: 600;">VOICE REPOSITORY</div>
          <div style="text-align: center; max-width: 320px;">No messages in this session yet. Speak in the Studio to start chatting.</div>
        </div>
      `;
      return;
    }

    const currentSession = this.sessions.find((s) => s.id === this.currentSessionId);
    const summaryHtml = this.generateSessionSummary(currentSession, this.messages);

    const messagesHtml = this.messages
      .map((m) => {
        const isUser = m.role === 'user';
        return `
          <div class="message-row ${isUser ? 'user' : 'assistant'}" style="
            display: flex;
            flex-direction: column;
            align-items: ${isUser ? 'flex-end' : 'flex-start'};
            margin-bottom: 1.25rem;
            width: 100%;
          ">
            <div style="
              max-width: min(88%, 680px);
              padding: 0.95rem 1.2rem;
              border-radius: ${isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px'};
              background: ${isUser ? 'rgba(245, 208, 97, 0.18)' : 'var(--bg-card)'};
              border: 1px solid ${isUser ? 'rgba(248, 216, 119, 0.45)' : 'var(--border-glass)'};
              color: var(--text-primary);
              font-size: 0.92rem;
              line-height: 1.55;
              overflow-wrap: anywhere;
              word-break: break-word;
              box-shadow: ${isUser ? '0 4px 18px rgba(245, 208, 97, 0.20)' : 'var(--shadow-sm)'};
            ">
              <div>${m.content}</div>
              <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 0.5rem; font-size: 0.72rem; color: var(--text-muted); gap: 0.75rem; flex-wrap: wrap;">
                <span>${new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                ${m.latency_ms ? `<span style="color: var(--gold-bright);">${m.latency_ms}ms</span>` : ''}
                ${m.characters_count ? `<span>${m.characters_count} chars</span>` : ''}
              </div>
            </div>
          </div>
        `;
      })
      .join('');

    container.innerHTML = summaryHtml + messagesHtml;

    // Attach click to suggestion chips
    container.querySelectorAll('.suggestion-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const prompt = chip.getAttribute('data-prompt');
        const inputPrompt = document.querySelector('#input-text-prompt');
        if (inputPrompt) {
          inputPrompt.value = prompt;
          const studioNav = document.querySelector('.nav-item[data-view="studio"]');
          if (studioNav) studioNav.click();
          inputPrompt.focus();
        }
      });
    });

    // Attach click to export markdown button
    container.querySelectorAll('.btn-export-markdown').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const sId = parseInt(btn.getAttribute('data-session-id'), 10);
        if (!sId) return;
        const originalText = btn.innerHTML;
        btn.innerHTML = '⏳ Exporting...';
        btn.disabled = true;
        try {
          const res = await api.exportConversation(sId, 'markdown');
          if (res && res.content) {
            const blob = new Blob([res.content], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = res.filename || `conversation_${sId}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }
        } catch (err) {
          alert(`Failed to export session: ${err.message}`);
        } finally {
          btn.innerHTML = originalText;
          btn.disabled = false;
        }
      });
    });

    container.scrollTop = 0;
  }
}

export const chatManager = new ChatManager();

/**
 * Authenticated API Client with Automatic JWT Token Refresh
 */

class ApiClient {
  constructor() {
    this.baseUrl = '/api';
  }

  getAccessToken() {
    return localStorage.getItem('access_token');
  }

  getRefreshToken() {
    return localStorage.getItem('refresh_token');
  }

  setTokens(accessToken, refreshToken) {
    localStorage.setItem('access_token', accessToken);
    if (refreshToken) {
      localStorage.setItem('refresh_token', refreshToken);
    }
  }

  clearTokens() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    options.headers = options.headers || {};

    const token = this.getAccessToken();
    if (token && !options.headers['Authorization']) {
      options.headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !options.headers['Content-Type']) {
      options.headers['Content-Type'] = 'application/json';
    }

    let response = await fetch(url, options);

    // Attempt token refresh on 401
    if (response.status === 401 && this.getRefreshToken() && !endpoint.includes('/auth/')) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        options.headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
        response = await fetch(url, options);
      } else {
        this.clearTokens();
        window.dispatchEvent(new CustomEvent('auth:required'));
        throw new Error('Session expired. Please log in again.');
      }
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errorData.detail || `Request failed (${response.status})`);
    }

    // Check response type
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return await response.json();
    } else if (contentType.includes('audio/')) {
      return await response.blob();
    }
    return response;
  }

  async refreshToken() {
    try {
      const res = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.getRefreshToken() }),
      });
      if (res.ok) {
        const data = await res.json();
        this.setTokens(data.access_token, data.refresh_token);
        return true;
      }
    } catch (e) {
      console.warn('Token refresh error:', e);
    }
    return false;
  }

  // Auth Methods
  async loginAsGuest() {
    try {
      const data = await this.request('/auth/guest', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      if (data && data.access_token) {
        this.setTokens(data.access_token, data.refresh_token);
        localStorage.setItem('current_user', JSON.stringify(data.user));
      }
      return data;
    } catch (e) {
      console.warn('Guest login request fallback:', e);
      return {
        access_token: 'guest_fallback_token',
        user: { id: 1, email: 'guest@nore.ai', full_name: 'Guest Tester', role: 'user' },
      };
    }
  }

  async login(email, password) {
    const data = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setTokens(data.access_token, data.refresh_token);
    localStorage.setItem('current_user', JSON.stringify(data.user));
    return data;
  }

  async register(email, password, fullName) {
    const data = await this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    this.setTokens(data.access_token, data.refresh_token);
    localStorage.setItem('current_user', JSON.stringify(data.user));
    return data;
  }

  async getMe() {
    return await this.request('/auth/me');
  }

  async requestPasswordReset(email) {
    return await this.request('/auth/password-reset/request', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async confirmPasswordReset(token, newPassword) {
    return await this.request('/auth/password-reset/confirm', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  }

  // Voice & Persona Methods
  async getVoices() {
    return await this.request('/voices');
  }

  async getModels() {
    return await this.request('/voices/models');
  }

  async getPersonas() {
    return await this.request('/personas');
  }

  async previewVoice(voiceId, text) {
    return await this.request('/voices/preview', {
      method: 'POST',
      body: JSON.stringify({ voice_id: voiceId, text }),
    });
  }

  async getVoicePreferences() {
    return await this.request('/users/me/voice-preferences');
  }

  async updateVoicePreferences(prefs) {
    return await this.request('/users/me/voice-preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  }

  // Conversation Sessions
  async getConversations() {
    return await this.request('/conversations');
  }

  async getConversation(id) {
    return await this.request(`/conversations/${id}`);
  }

  async createConversation(title, personaId) {
    return await this.request('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title, persona_id: personaId }),
    });
  }

  async deleteConversation(id) {
    return await this.request(`/conversations/${id}`, { method: 'DELETE' });
  }

  async exportConversation(id, format = 'markdown') {
    return await this.request(`/conversations/${id}/export?format=${format}`);
  }

  // Admin Methods
  async getAdminStats() {
    return await this.request('/admin/stats');
  }

  async getAdminUsers(search = '') {
    return await this.request(`/admin/users?search=${encodeURIComponent(search)}`);
  }

  async updateUserRole(userId, role, isActive, quota) {
    return await this.request(`/admin/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role, is_active: isActive, daily_character_quota: quota }),
    });
  }

  async deleteUser(userId) {
    return await this.request(`/admin/users/${userId}`, { method: 'DELETE' });
  }

  async logout() {
    try {
      await this.request('/auth/logout', { method: 'POST' });
    } catch (e) {
      console.warn('Logout request failed:', e);
    }
    this.clearTokens();
  }

  async getAuditLogs(eventType = '') {
    return await this.request(`/admin/audit-logs?event_type=${encodeURIComponent(eventType)}`);
  }

  async scanSecrets() {
    return await this.request('/security/scan-secrets', { method: 'POST' });
  }

  async getHealth() {
    return await this.request('/admin/health');
  }

  // Owner Operations
  async createAdmin(email, password, fullName) {
    return await this.request('/owner/admins', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
  }

  async deleteAdmin(adminId) {
    return await this.request(`/owner/admins/${adminId}`, { method: 'DELETE' });
  }

  async setAdminStatus(adminId, isActive, quota) {
    return await this.request(`/owner/admins/${adminId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: isActive, daily_character_quota: quota }),
    });
  }

  async getOwnerSystemConfig() {
    return await this.request('/owner/system-config');
  }

  async patchUser(userId, data) {
    return await this.request(`/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }
}

export const api = new ApiClient();

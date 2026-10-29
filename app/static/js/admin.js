/**
 * Admin Dashboard Controller: Telemetry Metrics, User RBAC Management, Audit Logs, and Secret Scanner
 */

import { api } from './api.js';

class AdminController {
  async init() {
    const currentUserJson = localStorage.getItem('current_user');
    const currentUser = currentUserJson ? JSON.parse(currentUserJson) : null;
    const isOwner = currentUser && currentUser.role === 'owner';

    const createAdminBtn = document.querySelector('#btn-open-create-admin');
    if (createAdminBtn) {
      createAdminBtn.style.display = isOwner ? 'inline-block' : 'none';
    }

    const configCard = document.querySelector('#owner-system-config-card');
    if (configCard) {
      configCard.style.display = isOwner ? 'block' : 'none';
      if (isOwner) {
        await this.loadSystemConfig();
      }
    }

    await this.loadStats();
    await this.loadUsers();
    await this.loadAuditLogs();
    this.attachEvents();
  }

  attachEvents() {
    const scanBtn = document.querySelector('#btn-run-secret-scan');
    if (scanBtn) {
      scanBtn.addEventListener('click', () => this.runSecretScan());
    }

    const userSearch = document.querySelector('#admin-user-search');
    if (userSearch) {
      userSearch.addEventListener('input', (e) => this.loadUsers(e.target.value));
    }

    const openCreateAdminBtn = document.querySelector('#btn-open-create-admin');
    if (openCreateAdminBtn) {
      openCreateAdminBtn.addEventListener('click', () => {
        const modal = document.querySelector('#modal-create-admin');
        if (modal) modal.classList.add('active');
      });
    }

    const formCreateAdmin = document.querySelector('#form-create-admin');
    if (formCreateAdmin) {
      formCreateAdmin.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.querySelector('#admin-create-email').value.trim();
        const password = document.querySelector('#admin-create-password').value;
        const name = document.querySelector('#admin-create-name').value.trim();
        try {
          await api.createAdmin(email, password, name);
          const modal = document.querySelector('#modal-create-admin');
          if (modal) modal.classList.remove('active');
          formCreateAdmin.reset();
          await this.loadUsers();
          await this.loadStats();
          alert('Admin account created successfully!');
        } catch (err) {
          alert('Failed to create admin: ' + err.message);
        }
      });
    }
  }

  async loadSystemConfig() {
    const card = document.querySelector('#owner-system-config-card');
    if (!card) return;
    try {
      const cfg = await api.getOwnerSystemConfig();
      document.querySelector('#cfg-elevenlabs-status').textContent = cfg.elevenlabs.status;
      document.querySelector('#cfg-elevenlabs-key').textContent = cfg.elevenlabs.masked_api_key;
      document.querySelector('#cfg-db-status').textContent = cfg.database.status;
      document.querySelector('#cfg-db-dialect').textContent = `Dialect: ${cfg.database.dialect}`;
      document.querySelector('#cfg-redis-status').textContent = cfg.redis.status;
      document.querySelector('#cfg-env-status').textContent = `${cfg.environment.toUpperCase()} (Prod: ${cfg.is_production})`;
    } catch (err) {
      console.warn('Could not load owner system config:', err);
    }
  }

  async loadStats() {
    try {
      const stats = await api.getAdminStats();
      document.querySelector('#stat-total-users').textContent = stats.total_users;
      document.querySelector('#stat-total-chars').textContent = stats.total_characters_consumed.toLocaleString();
      document.querySelector('#stat-total-cost').textContent = `$${stats.estimated_total_cost_usd.toFixed(3)}`;
      document.querySelector('#stat-el-status').textContent = stats.elevenlabs_key_status.toUpperCase();
      
      const elColor = stats.elevenlabs_key_status === 'connected' ? 'var(--status-listening)' : 'var(--status-thinking)';
      document.querySelector('#stat-el-status').style.color = elColor;

      if (stats.elevenlabs_subscription_tier) {
        document.querySelector('#stat-el-tier').textContent = `Tier: ${stats.elevenlabs_subscription_tier}`;
      }

      // Also load tech intelligence telemetry
      try {
        const token = api.getAccessToken();
        const techRes = await fetch('/api/admin/tech-telemetry', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (techRes.ok) {
          const techData = await techRes.json();
          if (document.querySelector('#stat-tech-searches')) {
            document.querySelector('#stat-tech-searches').textContent = (techData.total_searches || 0).toLocaleString();
          }
          if (document.querySelector('#stat-tech-cache-hits')) {
            document.querySelector('#stat-tech-cache-hits').textContent = (techData.cache_hits || 0).toLocaleString();
          }
          if (document.querySelector('#admin-search-provider-badge')) {
            document.querySelector('#admin-search-provider-badge').textContent = (techData.active_search_provider || 'AUTO').toUpperCase();
          }
        }
      } catch (e) {
        console.warn('Could not load tech telemetry:', e);
      }
    } catch (err) {
      console.warn('Could not load admin stats:', err);
    }
  }

  async loadUsers(search = '') {
    const tableBody = document.querySelector('#admin-users-tbody');
    if (!tableBody) return;

    try {
      const currentUserJson = localStorage.getItem('current_user');
      const currentUser = currentUserJson ? JSON.parse(currentUserJson) : null;
      const isOwner = currentUser && currentUser.role === 'owner';

      const users = await api.getAdminUsers(search);
      tableBody.innerHTML = users
        .map((u) => {
          const roleBadgeClass = `badge-${u.role}`;
          const activeBadgeClass = u.is_active ? 'badge-active' : 'badge-inactive';
          const isTargetOwner = u.role === 'owner';
          const isTargetAdmin = u.role === 'admin';

          let actionContent = '';
          if (isTargetOwner) {
            if (isOwner) {
              actionContent = `
                <button class="btn btn-secondary btn-edit-user" data-user='${JSON.stringify(u)}' style="padding: 4px 10px; font-size: 0.75rem;">
                  Edit Quota
                </button>
              `;
            } else {
              actionContent = `<span class="badge badge-protected">Protected Principal</span>`;
            }
          } else if (isTargetAdmin) {
            if (isOwner) {
              actionContent = `
                <div style="display: flex; gap: 0.35rem;">
                  <button class="btn btn-secondary btn-edit-user" data-user='${JSON.stringify(u)}' style="padding: 4px 10px; font-size: 0.75rem;">
                    Edit
                  </button>
                  <button class="btn btn-secondary btn-delete-admin" data-id="${u.id}" data-email="${u.email}" style="padding: 4px 8px; font-size: 0.75rem; color: var(--status-danger);" title="Delete Admin">
                    &times;
                  </button>
                </div>
              `;
            } else {
              actionContent = `<span style="font-size: 0.75rem; color: var(--text-muted); font-style: italic;">Peer Admin</span>`;
            }
          } else {
            actionContent = `
              <div style="display: flex; gap: 0.35rem;">
                <button class="btn btn-secondary btn-edit-user" data-user='${JSON.stringify(u)}' style="padding: 4px 10px; font-size: 0.75rem;">
                  Edit
                </button>
                <button class="btn btn-secondary btn-delete-user" data-id="${u.id}" data-email="${u.email}" style="padding: 4px 8px; font-size: 0.75rem; color: var(--status-danger);">
                  &times;
                </button>
              </div>
            `;
          }

          return `
            <tr>
              <td><strong>#${u.id}</strong></td>
              <td>
                <div style="font-weight: 600; color: var(--text-primary);">${u.email}</div>
                <div style="font-size: 0.78rem; color: var(--text-muted);">${u.full_name || 'No name'}</div>
              </td>
              <td><span class="badge ${roleBadgeClass}">${isTargetOwner ? 'OWNER' : u.role.toUpperCase()}</span></td>
              <td><span class="badge ${activeBadgeClass}">${u.is_active ? 'Active' : 'Disabled'}</span></td>
              <td>${u.daily_character_quota.toLocaleString()}</td>
              <td>${actionContent}</td>
            </tr>
          `;
        })
        .join('');

      tableBody.querySelectorAll('.btn-edit-user').forEach((btn) => {
        btn.addEventListener('click', () => {
          const userData = JSON.parse(btn.getAttribute('data-user'));
          this.openEditUserModal(userData);
        });
      });

      tableBody.querySelectorAll('.btn-delete-user').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const uId = btn.getAttribute('data-id');
          const uEmail = btn.getAttribute('data-email');
          if (confirm(`Are you sure you want to permanently delete user account ${uEmail}?`)) {
            try {
              await api.deleteUser(uId);
              await this.loadUsers(search);
              alert('User deleted successfully.');
            } catch (err) {
              alert('Delete failed: ' + err.message);
            }
          }
        });
      });

      tableBody.querySelectorAll('.btn-delete-admin').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const uId = btn.getAttribute('data-id');
          const uEmail = btn.getAttribute('data-email');
          if (confirm(`Owner Action: Are you sure you want to permanently delete Admin account ${uEmail}? All their active sessions will be revoked.`)) {
            try {
              await api.deleteAdmin(uId);
              await this.loadUsers(search);
              await this.loadStats();
              alert('Admin deleted successfully.');
            } catch (err) {
              alert('Delete failed: ' + err.message);
            }
          }
        });
      });
    } catch (err) {
      console.error('Error loading users:', err);
    }
  }

  openEditUserModal(user) {
    const modal = document.querySelector('#modal-edit-user');
    if (!modal) return;

    const currentUserJson = localStorage.getItem('current_user');
    const currentUser = currentUserJson ? JSON.parse(currentUserJson) : null;
    const isOwner = currentUser && currentUser.role === 'owner';
    const isTargetOwner = user.role === 'owner';

    document.querySelector('#edit-user-id').value = user.id;
    document.querySelector('#edit-user-email').value = user.email;
    document.querySelector('#edit-user-active').checked = user.is_active;
    document.querySelector('#edit-user-quota').value = user.daily_character_quota;

    const roleSelect = document.querySelector('#edit-user-role');
    const activeCheckbox = document.querySelector('#edit-user-active');

    if (isTargetOwner) {
      roleSelect.innerHTML = `<option value="owner">Owner (Protected Principal)</option>`;
      roleSelect.disabled = true;
      activeCheckbox.disabled = true; // Owner cannot be disabled
    } else {
      activeCheckbox.disabled = false;
      if (isOwner) {
        roleSelect.disabled = false;
        roleSelect.innerHTML = `
          <option value="user" ${user.role === 'user' ? 'selected' : ''}>User (Standard Access)</option>
          <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin (Management Access)</option>
        `;
      } else {
        // Admins cannot change roles
        roleSelect.disabled = true;
        roleSelect.innerHTML = `<option value="user">User (Standard Access)</option>`;
      }
    }

    modal.classList.add('active');

    const form = document.querySelector('#form-edit-user');
    form.onsubmit = async (e) => {
      e.preventDefault();
      const role = roleSelect.disabled ? undefined : roleSelect.value;
      const isActive = isTargetOwner ? true : activeCheckbox.checked;
      const quota = parseInt(document.querySelector('#edit-user-quota').value, 10);

      try {
        await api.updateUserRole(user.id, role, isActive, quota);
        modal.classList.remove('active');
        await this.loadUsers();
        alert('User updated successfully.');
      } catch (err) {
        alert('Failed to update user: ' + err.message);
      }
    };
  }

  async loadAuditLogs() {
    const tableBody = document.querySelector('#admin-audit-tbody');
    if (!tableBody) return;

    try {
      const logs = await api.getAuditLogs();
      tableBody.innerHTML = logs.slice(0, 30)
        .map((l) => {
          const dateStr = new Date(l.created_at).toLocaleString();
          return `
            <tr>
              <td><span style="font-family: monospace; font-size: 0.78rem;">${dateStr}</span></td>
              <td><strong>${l.event_type}</strong></td>
              <td>${l.email || 'N/A'}</td>
              <td><span class="badge ${l.severity === 'WARNING' ? 'badge-inactive' : 'badge-user'}">${l.severity}</span></td>
              <td><span style="font-size: 0.82rem; color: var(--text-muted);">${l.details || ''}</span></td>
            </tr>
          `;
        })
        .join('');
    } catch (err) {
      console.warn('Could not load audit logs:', err);
    }
  }

  async runSecretScan() {
    const scanBtn = document.querySelector('#btn-run-secret-scan');
    const resultBox = document.querySelector('#secret-scan-results');
    if (scanBtn) scanBtn.textContent = 'Scanning...';

    try {
      const res = await api.scanSecrets();
      if (scanBtn) scanBtn.textContent = 'Run Secret Scan';

      if (resultBox) {
        resultBox.style.display = 'block';
        if (res.status === 'clean') {
          resultBox.innerHTML = `
            <div style="padding: 1rem; background: rgba(16, 185, 129, 0.15); border: 1px solid var(--status-listening); border-radius: var(--radius-md); color: #34D399;">
              <strong>SECURITY AUDIT PASSED:</strong> 0 secrets detected across ${res.scanned_files_count} repository files.
            </div>
          `;
        } else {
          resultBox.innerHTML = `
            <div style="padding: 1rem; background: rgba(239, 68, 68, 0.15); border: 1px solid var(--status-danger); border-radius: var(--radius-md); color: #F87171;">
              <strong>SECURITY WARNING:</strong> ${res.findings_count} potential secrets detected!
              <pre style="margin-top: 0.5rem; font-size: 0.75rem;">${JSON.stringify(res.findings, null, 2)}</pre>
            </div>
          `;
        }
      }
    } catch (err) {
      if (scanBtn) scanBtn.textContent = 'Run Secret Scan';
      alert('Secret scan error: ' + err.message);
    }
  }
}

export const adminController = new AdminController();

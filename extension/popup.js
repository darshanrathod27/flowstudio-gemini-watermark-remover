// FlowStudio Pro - Popup Controller (Manifest V3, v3.7.0)
(function () {
  'use strict';

  const API_BASE = "http://127.0.0.1:8765";
  const CLOUDFLARE_VERSION_URL = "https://flowstudio-api.flowstudio-app.workers.dev/api/version";
  const GITHUB_VERSION_URL = "https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json";
  const CURRENT_VERSION = "3.7.0";

  // Elements
  const hwPill = document.getElementById('hw-pill');
  const statusDot = document.getElementById('status-dot');
  const hwLabel = document.getElementById('hw-label');
  const controlsCard = document.getElementById('controls-card');
  const toggleEnabled = document.getElementById('toggle-enabled');
  const pausedIndicator = document.getElementById('paused-indicator');
  const toggleSuffix = document.getElementById('toggle-suffix');
  const toggleHiddenLogo = document.getElementById('toggle-hidden-logo');
  const selectUpscale = document.getElementById('select-upscale');
  const selectAutoflow = document.getElementById('select-autoflow');
  const activityList = document.getElementById('activity-list');
  const activityBadge = document.getElementById('activity-badge');
  const clearHistoryBtn = document.getElementById('clear-history-btn');
  const btnOpenStudio = document.getElementById('btn-open-studio');
  const btnUpdateNow = document.getElementById('btn-update-now');
  const updateStatus = document.getElementById('update-status');
  const btnCheckUpdate = document.getElementById('btn-check-update');
  const versionBadge = document.getElementById('version-badge');
  const updateBanner = document.getElementById('update-banner');
  const updateBannerText = document.getElementById('update-banner-text');
  const updateVersion = document.getElementById('update-version');

  let isStarting = false;

  // SVG Icons for 22x22 Micro-Buttons
  const SVG_PAUSE = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>`;
  const SVG_RESUME = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"/></svg>`;
  const SVG_CANCEL = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>`;
  const SVG_REMOVE = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

  function normalizeSemver(v) {
    return String(v || "0.0.0").trim().replace(/^v+/i, "");
  }

  // 1. Load Settings
  chrome.storage.local.get({
    enabled: false,
    addCleanSuffix: false,
    removeHiddenLogo: false,
    upscaleMode: 'off',
    autoFlowMode: 'off',
    updateAvailable: false,
    remoteVersion: ''
  }, (items) => {
    toggleEnabled.checked = items.enabled;
    toggleSuffix.checked = items.addCleanSuffix;
    if (toggleHiddenLogo) toggleHiddenLogo.checked = !!items.removeHiddenLogo;
    selectUpscale.value = items.upscaleMode || 'off';
    if (selectAutoflow) selectAutoflow.value = items.autoFlowMode || 'off';
    updateToggleUI(items.enabled);

    if (updateBanner && items.updateAvailable) {
      const cleanVer = normalizeSemver(items.remoteVersion) || CURRENT_VERSION;
      updateBanner.style.display = 'block';
      if (updateBannerText) {
        updateBannerText.innerHTML = `v<strong id="update-version">${cleanVer}</strong> ready`;
      } else if (updateVersion) {
        updateVersion.textContent = cleanVer;
      }
    }
  });

  function updateToggleUI(isEnabled) {
    if (isEnabled) {
      controlsCard.classList.remove('dimmed');
      pausedIndicator.style.display = 'none';
    } else {
      controlsCard.classList.add('dimmed');
      pausedIndicator.style.display = 'inline-block';
    }
  }

  // 2. Control Event Listeners
  toggleEnabled.addEventListener('change', () => {
    const isEnabled = toggleEnabled.checked;
    updateToggleUI(isEnabled);

    chrome.runtime.sendMessage({ type: "TOGGLE_ENABLED", enabled: isEnabled }, () => {
      if (isEnabled) {
        setStartingUI();
      }
      checkHealth();
    });
  });

  toggleSuffix.addEventListener('change', () => {
    chrome.storage.local.set({ addCleanSuffix: toggleSuffix.checked });
  });

  if (toggleHiddenLogo) {
    toggleHiddenLogo.addEventListener('change', () => {
      chrome.storage.local.set({ removeHiddenLogo: toggleHiddenLogo.checked });
    });
  }

  selectUpscale.addEventListener('change', () => {
    chrome.storage.local.set({ upscaleMode: selectUpscale.value });
  });

  if (selectAutoflow) {
    selectAutoflow.addEventListener('change', () => {
      chrome.storage.local.set({ autoFlowMode: selectAutoflow.value });
    });
  }

  // Header pill click to wake server manually (silently, zero black console, zero surprise browser tabs)
  hwPill.addEventListener('click', () => {
    if (!statusDot.classList.contains('online')) {
      setStartingUI();
      chrome.runtime.sendMessage({ type: "ENSURE_SERVER_ONLINE" }, () => {
        checkHealth();
      });
    }
  });

  function setStartingUI() {
    isStarting = true;
    statusDot.className = 'status-dot starting';
    hwLabel.textContent = "Starting...";
  }

  // Batch Studio Button: ensure server online first, wait for 200 OK, then open tab
  btnOpenStudio.addEventListener('click', async () => {
    btnOpenStudio.disabled = true;
    const originalText = btnOpenStudio.textContent;
    btnOpenStudio.textContent = "Starting...";

    try {
      const bootRes = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ type: "ENSURE_SERVER_ONLINE" }, resolve);
      });

      if (bootRes && bootRes.online) {
        chrome.tabs.create({ url: API_BASE });
      } else {
        // Fallback polling up to 6s
        let confirmed = false;
        for (let i = 0; i < 15; i++) {
          try {
            const resp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(600) });
            if (resp.ok) {
              confirmed = true;
              break;
            }
          } catch (_) {}
          await new Promise(r => setTimeout(r, 400));
        }

        if (confirmed) {
          chrome.tabs.create({ url: API_BASE });
        } else {
          hwLabel.textContent = "Start failed";
          statusDot.className = 'status-dot offline';
        }
      }
    } catch (_) {
      hwLabel.textContent = "Start failed";
      statusDot.className = 'status-dot offline';
    } finally {
      btnOpenStudio.disabled = false;
      btnOpenStudio.textContent = originalText;
    }
  });

  // Clear History Button
  if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', async () => {
      clearHistoryBtn.disabled = true;
      const originalText = clearHistoryBtn.textContent;
      clearHistoryBtn.textContent = "Cleared";

      try {
        await fetch(`${API_BASE}/api/jobs/clear-history?source=extension`, { method: 'POST' });
        fetchRecentActivity();
      } catch (_) {}

      setTimeout(() => {
        clearHistoryBtn.textContent = originalText;
      }, 1500);
    });
  }

  // Update Now Handler
  if (btnUpdateNow) {
    btnUpdateNow.addEventListener('click', () => {
      btnUpdateNow.disabled = true;
      btnUpdateNow.textContent = "Updating...";
      if (updateStatus) {
        updateStatus.style.display = 'block';
        updateStatus.textContent = "Downloading and updating FlowStudio...";
        updateStatus.style.color = '#58a6ff';
      }

      chrome.runtime.sendMessage({ type: "TRIGGER_UPDATE" }, (res) => {
        if (chrome.runtime.lastError) {
          const err = chrome.runtime.lastError.message || "Update error";
          if (updateStatus) {
            updateStatus.textContent = `Err: ${err}`;
            updateStatus.style.color = '#da3633';
          }
          btnUpdateNow.disabled = false;
          btnUpdateNow.textContent = "Update Now";
        } else if (res && res.ok) {
          chrome.storage.local.set({ updateAvailable: false });
          const cleanVer = normalizeSemver(res.version) || CURRENT_VERSION;
          if (updateStatus) {
            updateStatus.textContent = `✓ Server & Ext v${cleanVer} ready! Reloading...`;
            updateStatus.style.color = '#238636';
          }
          setTimeout(() => {
            chrome.runtime.reload();
            window.close();
          }, 1400);
        } else {
          const errMsg = (res && res.error) || "Update failed";
          if (updateStatus) {
            updateStatus.textContent = `Failed: ${errMsg}`;
            updateStatus.style.color = '#da3633';
          }
          btnUpdateNow.disabled = false;
          btnUpdateNow.textContent = "Retry";
        }
      });
    });
  }

  // Check for updates button
  if (btnCheckUpdate) {
    btnCheckUpdate.addEventListener('click', async () => {
      btnCheckUpdate.style.transform = 'rotate(180deg)';
      setTimeout(() => { btnCheckUpdate.style.transform = ''; }, 400);

      try {
        let data = null;
        try {
          const cfRes = await fetch(CLOUDFLARE_VERSION_URL, { cache: "no-store", signal: AbortSignal.timeout(3000) });
          if (cfRes.ok) data = await cfRes.json();
        } catch (_) {}

        if (!data) {
          const ghRes = await fetch(GITHUB_VERSION_URL, { cache: "no-store", signal: AbortSignal.timeout(4000) });
          if (ghRes.ok) data = await ghRes.json();
        }

        const remoteVer = data && data.version ? normalizeSemver(data.version) : null;
        if (remoteVer && remoteVer !== CURRENT_VERSION) {
          chrome.storage.local.set({
            updateAvailable: true,
            remoteVersion: remoteVer
          });
          if (updateBanner) updateBanner.style.display = 'block';
          if (updateBannerText) {
            updateBannerText.innerHTML = `v<strong id="update-version">${remoteVer}</strong> ready`;
          } else if (updateVersion) {
            updateVersion.textContent = remoteVer;
          }
        } else {
          if (versionBadge) {
            const origText = versionBadge.textContent;
            versionBadge.textContent = "Up to date";
            versionBadge.style.color = "#3fb950";
            setTimeout(() => {
              versionBadge.textContent = origText;
              versionBadge.style.color = "";
            }, 2000);
          }
        }
      } catch (_) {
        if (versionBadge) {
          const origText = versionBadge.textContent;
          versionBadge.textContent = "Offline";
          setTimeout(() => { versionBadge.textContent = origText; }, 2000);
        }
      }
    });
  }

  // 3. Health Polling
  async function checkHealth() {
    try {
      const resp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(1200) });
      if (resp.ok) {
        const data = await resp.json();
        isStarting = false;
        statusDot.className = 'status-dot online';
        if (data.cuda_available) {
          const shortGpu = (data.gpu_name || 'GPU')
            .replace(/NVIDIA /i, '')
            .replace(/GeForce /i, '')
            .replace(/Laptop GPU/i, '')
            .trim();
          hwLabel.textContent = shortGpu || 'RTX GPU';
        } else {
          hwLabel.textContent = 'CPU';
        }

        // Validate backend version sync
        if (data.version && versionBadge) {
          const cleanBackend = normalizeSemver(data.version);
          if (cleanBackend === CURRENT_VERSION) {
            versionBadge.title = `Server: v${cleanBackend} (verified in sync)`;
          } else {
            versionBadge.title = `Server: v${cleanBackend} (Extension: v${CURRENT_VERSION})`;
          }
        }
      } else {
        handleHealthFailure();
      }
    } catch (_) {
      handleHealthFailure();
    }
  }

  function handleHealthFailure() {
    if (isStarting) {
      statusDot.className = 'status-dot starting';
      hwLabel.textContent = 'Starting...';
    } else {
      statusDot.className = 'status-dot offline';
      hwLabel.textContent = 'Standby · Wake';
    }
  }

  // Broadcast listener from background.js
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "SERVER_STATUS") {
      if (msg.status === "online") {
        isStarting = false;
        checkHealth();
      } else if (msg.status === "starting") {
        setStartingUI();
      } else {
        isStarting = false;
        handleHealthFailure();
      }
    }
  });

  // 4. Live Activity Polling & Systematic Micro-Buttons
  async function fetchRecentActivity() {
    try {
      const resp = await fetch(`${API_BASE}/api/jobs?source=extension&limit=10`, { signal: AbortSignal.timeout(1200) });
      if (!resp.ok) return;
      const jobs = await resp.json();
      renderActivity(jobs);
    } catch (_) {}
  }

  function renderActivity(jobs) {
    if (!jobs || jobs.length === 0) {
      activityList.innerHTML = '<div class="empty-state">Ready — download media from Flow</div>';
      activityBadge.textContent = '0';
      if (clearHistoryBtn) clearHistoryBtn.disabled = true;
      return;
    }

    activityBadge.textContent = `${jobs.length}`;

    // Enable Clear All if any finished items exist
    const hasFinished = jobs.some(j => ['completed', 'cancelled', 'failed'].includes(j.status));
    if (clearHistoryBtn) clearHistoryBtn.disabled = !hasFinished;

    let html = '';

    for (const j of jobs) {
      const isVid = j.file_type === 'video';
      const tag = isVid ? 'VID' : 'IMG';
      const pct = Math.round(j.progress_pct || 0);

      let actionButtons = '';
      let bottomLine = '';

      if (j.status === 'processing') {
        actionButtons = `
          <button class="micro-btn pause" data-action="pause" data-id="${j.id}" title="Pause job">${SVG_PAUSE}</button>
          <button class="micro-btn cancel" data-action="cancel" data-id="${j.id}" title="Cancel job">${SVG_CANCEL}</button>
        `;
        const etaText = j.eta_sec ? ` · ${j.eta_sec}s` : '';
        bottomLine = `
          <div class="job-bottom">
            <div class="job-progress-bar"><div class="job-progress-fill" style="width: ${pct}%;"></div></div>
            <span class="job-progress-meta">${pct}%${etaText}</span>
          </div>
        `;
      } else if (j.status === 'paused') {
        actionButtons = `
          <button class="micro-btn resume" data-action="resume" data-id="${j.id}" title="Resume job">${SVG_RESUME}</button>
          <button class="micro-btn cancel" data-action="cancel" data-id="${j.id}" title="Cancel job">${SVG_CANCEL}</button>
        `;
        bottomLine = `
          <div class="job-bottom">
            <div class="job-progress-bar"><div class="job-progress-fill paused" style="width: ${pct}%;"></div></div>
            <span class="job-progress-meta" style="color: #d29922;">Paused · ${pct}%</span>
          </div>
        `;
      } else if (j.status === 'queued') {
        actionButtons = `
          <button class="micro-btn cancel" data-action="cancel" data-id="${j.id}" title="Cancel job">${SVG_CANCEL}</button>
        `;
        bottomLine = `
          <div class="job-bottom">
            <div class="job-progress-bar"><div class="job-progress-fill" style="width: 0%;"></div></div>
            <span class="job-progress-meta">Queued</span>
          </div>
        `;
      } else if (j.status === 'completed') {
        const copyChip = j.copied_to_clipboard ? '<span class="chip-copied" title="Copied — Ctrl+V">📋</span>' : '';
        actionButtons = `
          <span class="badge-status success">✓ ${copyChip}</span>
          <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
        `;
      } else if (j.status === 'cancelled') {
        actionButtons = `
          <span class="badge-status muted">Cancelled</span>
          <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
        `;
      } else {
        actionButtons = `
          <span class="badge-status danger">Failed</span>
          <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
        `;
      }

      html += `
        <div class="job-item" data-id="${j.id}">
          <div class="job-top">
            <div class="job-meta">
              <span class="job-tag">${tag}</span>
              <span class="job-filename" title="${escapeHtml(j.filename)}">${escapeHtml(j.filename)}</span>
            </div>
            <div class="job-actions">
              ${actionButtons}
            </div>
          </div>
          ${bottomLine}
        </div>
      `;
    }

    activityList.innerHTML = html;

    // Attach event listeners to micro-buttons
    activityList.querySelectorAll('.micro-btn').forEach((btn) => {
      btn.onclick = async () => {
        const action = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id');
        btn.disabled = true;

        try {
          if (action === 'pause') {
            await fetch(`${API_BASE}/api/jobs/${id}/pause`, { method: 'POST' });
          } else if (action === 'resume') {
            await fetch(`${API_BASE}/api/jobs/${id}/resume`, { method: 'POST' });
          } else if (action === 'cancel') {
            await fetch(`${API_BASE}/api/jobs/${id}/cancel`, { method: 'POST' });
          } else if (action === 'delete') {
            await fetch(`${API_BASE}/api/jobs/${id}`, { method: 'DELETE' });
          }
          fetchRecentActivity();
        } catch (_) {}
      };
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Initial Polls & Intervals
  checkHealth();
  fetchRecentActivity();
  setInterval(checkHealth, 3500);
  setInterval(fetchRecentActivity, 800);
})();

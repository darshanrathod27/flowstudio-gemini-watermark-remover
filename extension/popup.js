// FlowStudio Pro - Popup Controller (Manifest V3, v3.3.0)
(function () {
  'use strict';

  const API_BASE = "http://127.0.0.1:8765";
  const CLOUDFLARE_VERSION_URL = "https://flowstudio-api.flowstudio-app.workers.dev/api/version";
  const GITHUB_VERSION_URL = "https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json";
  const CURRENT_VERSION = "3.3.0";

  const statusDot = document.getElementById('status-dot');
  const hwLabel = document.getElementById('hw-label');
  const controlsCard = document.getElementById('controls-card');
  const toggleEnabled = document.getElementById('toggle-enabled');
  const subtleNotice = document.getElementById('subtle-notice');
  const toggleAutoWake = document.getElementById('toggle-autowake');
  const toggleSuffix = document.getElementById('toggle-suffix');
  const selectUpscale = document.getElementById('select-upscale');
  const activityList = document.getElementById('activity-list');
  const activityBadge = document.getElementById('activity-badge');
  const btnOpenStudio = document.getElementById('btn-open-studio');
  const btnUpdateNow = document.getElementById('btn-update-now');
  const updateStatus = document.getElementById('update-status');
  const btnCheckUpdate = document.getElementById('btn-check-update');
  const versionBadge = document.getElementById('version-badge');

  let hasExplicitNativeError = false;
  let startPollDeadline = 0;
  let startPollInterval = null;

  // 1. Load Settings
  chrome.storage.local.get({
    enabled: false,
    autoWake: true,
    addCleanSuffix: false,
    upscaleMode: 'off',
    updateAvailable: false,
    remoteVersion: '',
    releaseUrl: ''
  }, (items) => {
    toggleEnabled.checked = items.enabled;
    toggleAutoWake.checked = items.autoWake;
    toggleSuffix.checked = items.addCleanSuffix;
    selectUpscale.value = items.upscaleMode || 'off';
    updateControlsState(items.enabled);

    // Show update banner if update detected
    const updateBanner = document.getElementById('update-banner');
    const updateVersion = document.getElementById('update-version');
    if (updateBanner && items.updateAvailable) {
      updateBanner.style.display = 'block';
      if (updateVersion) updateVersion.textContent = `v${items.remoteVersion || CURRENT_VERSION}`;
    }
  });

  function updateControlsState(isEnabled) {
    if (isEnabled) {
      controlsCard.classList.remove('disabled');
      subtleNotice.style.display = 'none';
    } else {
      controlsCard.classList.add('disabled');
      subtleNotice.style.display = 'block';
    }
  }

  function startBootPolling() {
    startPollDeadline = Date.now() + 25000;
    hwLabel.textContent = "Starting GPU...";
    statusDot.className = 'status-dot';
    if (startPollInterval) clearInterval(startPollInterval);
    startPollInterval = setInterval(checkHealth, 600);
  }

  // 2. Settings Listeners & Native Host Trigger
  toggleEnabled.addEventListener('change', async () => {
    const isEnabled = toggleEnabled.checked;
    await chrome.storage.local.set({ enabled: isEnabled });
    updateControlsState(isEnabled);
    hasExplicitNativeError = false;

    if (isEnabled) {
      // Check if server is already online before firing start
      try {
        const resp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(800) });
        if (resp.ok) {
          checkHealth();
          return;
        }
      } catch (_) {}

      startBootPolling();

      chrome.runtime.sendMessage({ cmd: "start" }, (resp) => {
        if (chrome.runtime.lastError) {
          const err = chrome.runtime.lastError.message || "Message error";
          console.error("[FlowStudio Popup] Extension runtime error:", err);
          hasExplicitNativeError = true;
          startPollDeadline = 0;
          if (startPollInterval) { clearInterval(startPollInterval); startPollInterval = null; }
          hwLabel.textContent = `Err: ${err.slice(0, 16)}`;
          hwLabel.title = err;
          statusDot.className = 'status-dot offline';
        } else if (resp && resp.error) {
          console.error("[FlowStudio Popup] Native host error:", resp.error);
          hasExplicitNativeError = true;
          startPollDeadline = 0;
          if (startPollInterval) { clearInterval(startPollInterval); startPollInterval = null; }
          hwLabel.textContent = `Err: ${resp.error.slice(0, 16)}`;
          hwLabel.title = resp.error;
          statusDot.className = 'status-dot offline';
        } else {
          checkHealth();
        }
      });
    } else {
      // NOTE: Toggling OFF ONLY pauses download interception. NEVER kills the GPU server!
      startPollDeadline = 0;
      if (startPollInterval) { clearInterval(startPollInterval); startPollInterval = null; }
      checkHealth();
    }
  });

  toggleAutoWake.addEventListener('change', () => {
    chrome.storage.local.set({ autoWake: toggleAutoWake.checked });
  });

  toggleSuffix.addEventListener('change', () => {
    chrome.storage.local.set({ addCleanSuffix: toggleSuffix.checked });
  });

  selectUpscale.addEventListener('change', () => {
    chrome.storage.local.set({ upscaleMode: selectUpscale.value });
  });

  btnOpenStudio.addEventListener('click', async () => {
    // If server offline, wake it up in background so user lands on a live page
    try {
      const resp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(600) });
      if (!resp.ok) chrome.runtime.sendMessage({ cmd: "start" });
    } catch (_) {
      chrome.runtime.sendMessage({ cmd: "start" });
      startBootPolling();
    }
    chrome.tabs.create({ url: API_BASE });
  });

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
            updateStatus.textContent = `Err: ${err} (Run update.bat)`;
            updateStatus.style.color = '#da3633';
          }
          btnUpdateNow.disabled = false;
          btnUpdateNow.textContent = "Update Now";
        } else if (res && res.ok) {
          chrome.storage.local.set({ updateAvailable: false });
          if (updateStatus) {
            updateStatus.textContent = `✓ Updated to v${res.version || CURRENT_VERSION}! Reloading...`;
            updateStatus.style.color = '#238636';
          }
          setTimeout(() => {
            chrome.runtime.reload();
            window.close();
          }, 1200);
        } else {
          const errMsg = (res && res.error) || "Update failed";
          if (updateStatus) {
            updateStatus.textContent = `Failed: ${errMsg} (Run update.bat)`;
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

        if (data && data.version && data.version !== CURRENT_VERSION) {
          chrome.storage.local.set({
            updateAvailable: true,
            remoteVersion: data.version
          });
          const updateBanner = document.getElementById('update-banner');
          const updateVersion = document.getElementById('update-version');
          if (updateBanner) updateBanner.style.display = 'block';
          if (updateVersion) updateVersion.textContent = `v${data.version}`;
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
        hasExplicitNativeError = false;
        startPollDeadline = 0;
        if (startPollInterval) { clearInterval(startPollInterval); startPollInterval = null; }
        statusDot.className = 'status-dot online';
        if (data.cuda_available) {
          const shortGpu = (data.gpu_name || 'GPU').replace(/NVIDIA /i, '').replace(/GeForce /i, '').replace(/Laptop GPU/i, '').trim();
          hwLabel.textContent = shortGpu || 'RTX GPU';
        } else {
          hwLabel.textContent = 'CPU';
        }
      } else {
        handleHealthFailure();
      }
    } catch (_) {
      handleHealthFailure();
    }
  }

  function handleHealthFailure() {
    if (hasExplicitNativeError) return;

    if (Date.now() < startPollDeadline) {
      hwLabel.textContent = "Starting GPU...";
      statusDot.className = 'status-dot';
    } else {
      if (startPollInterval) { clearInterval(startPollInterval); startPollInterval = null; }
      statusDot.className = 'status-dot offline';
      hwLabel.textContent = 'Offline';
    }
  }

  // 4. Live Activity Polling
  async function fetchRecentActivity() {
    try {
      const resp = await fetch(`${API_BASE}/api/jobs?source=extension&limit=5`, { signal: AbortSignal.timeout(1200) });
      if (!resp.ok) return;
      const jobs = await resp.json();
      renderActivity(jobs);
    } catch (_) {}
  }

  function renderActivity(jobs) {
    if (!jobs || jobs.length === 0) {
      activityList.innerHTML = '<div class="empty-state">Download from Flow to auto-clean</div>';
      activityBadge.textContent = '0 items';
      return;
    }

    activityBadge.textContent = `${jobs.length} items`;
    let html = '';

    for (const j of jobs) {
      const isVid = j.file_type === 'video';
      const tag = isVid ? 'VID' : 'IMG';
      const pct = Math.round(j.progress_pct || 0);

      let statusHtml = '';
      if (j.status === 'processing' || j.status === 'queued') {
        statusHtml = `
          <span style="color:#58a6ff; font-weight:600;">${pct}%</span>
          <button class="job-btn-stop" data-id="${j.id}" title="Cancel processing">■</button>
        `;
      } else if (j.status === 'completed') {
        const copiedChip = j.copied_to_clipboard ? '<span class="chip-copied">📋 Copied</span>' : '';
        statusHtml = `<span class="job-status-badge saved">✓ Saved ${copiedChip}</span>`;
      } else if (j.status === 'cancelled') {
        statusHtml = '<span style="color:#8b949e; font-size:10px;">Cancelled</span>';
      } else {
        statusHtml = '<span style="color:#da3633; font-size:10px;">Failed</span>';
      }

      const progressBar = (j.status === 'processing') ? `
        <div class="job-progress-bar">
          <div class="job-progress-fill" style="width: ${pct}%;"></div>
        </div>
      ` : '';

      html += `
        <div class="job-item">
          <div class="job-top">
            <div class="job-meta">
              <span class="job-tag">${tag}</span>
              <span class="job-filename" title="${escapeHtml(j.filename)}">${escapeHtml(j.filename)}</span>
            </div>
            <div style="display:flex; align-items:center; gap:5px;">
              ${statusHtml}
            </div>
          </div>
          ${progressBar}
        </div>
      `;
    }

    activityList.innerHTML = html;

    // Attach stop button handlers
    document.querySelectorAll('.job-btn-stop').forEach((btn) => {
      btn.onclick = async () => {
        btn.disabled = true;
        const jobId = btn.getAttribute('data-id');
        try {
          await fetch(`${API_BASE}/api/jobs/${jobId}/cancel`, { method: 'POST' });
          fetchRecentActivity();
        } catch (_) {}
      };
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Initial runs and intervals
  checkHealth();
  fetchRecentActivity();
  setInterval(checkHealth, 4000);
  setInterval(fetchRecentActivity, 1000);
})();

// FlowStudio Pro - Popup Controller (Manifest V3, v4.0.3)
(function () {
  'use strict';

  const API_BASE = "http://127.0.0.1:8765";
  const CLOUDFLARE_VERSION_URL = "https://flowstudio-api.flowstudio-app.workers.dev/api/version";
  const GITHUB_VERSION_URL = "https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json";
  const CURRENT_VERSION = "4.0.3";

  // Elements
  const hwPill = document.getElementById('hw-pill');
  const statusDot = document.getElementById('status-dot');
  const hwLabel = document.getElementById('hw-label');
  const wakeRetryHint = document.getElementById('wake-retry-hint');
  const controlsCard = document.getElementById('controls-card');
  const toggleEnabled = document.getElementById('toggle-enabled');
  const pausedIndicator = document.getElementById('paused-indicator');
  const toggleSuffix = document.getElementById('toggle-suffix');
  const toggleProjectZip = document.getElementById('toggle-project-zip');
  const selectUpscale = document.getElementById('select-upscale');
  const selectAutoflow = document.getElementById('select-autoflow');
  const activityList = document.getElementById('activity-list');
  const activityBadge = document.getElementById('activity-badge');
  const activityToast = document.getElementById('activity-toast');
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
  let wakeWatchdogTimer = null;
  let wakeFastPollTimer = null;
  let retryHintTimer = null;
  let toastTimer = null;
  let lastJobsSignature = '';
  let syncReloadTriggered = false;

  // SVG Icons for 22x22 Micro-Buttons
  const SVG_PAUSE = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>`;
  const SVG_RESUME = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"/></svg>`;
  const SVG_CANCEL = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>`;
  const SVG_FOLDER = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
  const SVG_REMOVE = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

  function hasValidRuntime() {
    try {
      return typeof chrome !== "undefined" && !!(chrome && chrome.runtime && chrome.runtime.id);
    } catch (_) {
      return false;
    }
  }

  function normalizeSemver(v) {
    return String(v || "0.0.0").trim().replace(/^v+/i, "");
  }

  function compareSemver(a, b) {
    const pa = normalizeSemver(a).split(".").map(n => parseInt(n, 10) || 0);
    const pb = normalizeSemver(b).split(".").map(n => parseInt(n, 10) || 0);
    for (let i = 0; i < 3; i++) {
      const va = pa[i] || 0;
      const vb = pb[i] || 0;
      if (va > vb) return 1;
      if (va < vb) return -1;
    }
    return 0;
  }

  function getManifestVersion() {
    try {
      if (typeof chrome !== "undefined" && chrome && chrome.runtime && typeof chrome.runtime.getManifest === "function") {
        const mf = chrome.runtime.getManifest();
        if (mf && mf.version) return normalizeSemver(mf.version);
      }
    } catch (_) {}
    return CURRENT_VERSION;
  }

  function safeStorageSet(obj) {
    try {
      if (!hasValidRuntime() || !chrome.storage || !chrome.storage.local) return Promise.resolve(false);
      return chrome.storage.local.set(obj).catch(() => false);
    } catch (_) {
      return Promise.resolve(false);
    }
  }

  function safeStorageGet(defaults) {
    try {
      if (!hasValidRuntime() || !chrome.storage || !chrome.storage.local) return Promise.resolve({ ...defaults });
      return chrome.storage.local.get(defaults).catch(() => ({ ...defaults }));
    } catch (_) {
      return Promise.resolve({ ...defaults });
    }
  }

  function safeRuntimeSendMessage(payload, callback) {
    try {
      if (!hasValidRuntime() || typeof chrome.runtime.sendMessage !== "function") {
        if (callback) callback(null);
        return;
      }
      chrome.runtime.sendMessage(payload, (res) => {
        let rtErr = null;
        try { rtErr = chrome.runtime.lastError; } catch (_) {}
        if (callback) callback(rtErr ? null : res, rtErr);
      });
    } catch (e) {
      if (callback) callback(null, e);
    }
  }

  function safeRuntimeReload() {
    try {
      if (hasValidRuntime() && typeof chrome.runtime.reload === "function") {
        chrome.runtime.reload();
      }
    } catch (_) {}
  }

  function showActivityToast(msg, isError = false) {
    if (!activityToast) return;
    activityToast.textContent = msg;
    activityToast.className = isError ? 'activity-toast error' : 'activity-toast';
    activityToast.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      if (activityToast) activityToast.style.display = 'none';
    }, 3000);
  }

  // 10-Profile Chrome Auto-Sync: when another profile already updated backend, reload extension cleanly once
  async function syncProfileIfBackendNewer(backendVersionRaw) {
    const backendVer = normalizeSemver(backendVersionRaw);
    const manifestVer = getManifestVersion();
    if (!backendVer || compareSemver(backendVer, manifestVer) <= 0) return false;

    const stored = await safeStorageGet({
      lastKnownServerVersion: manifestVer,
      lastAutoReloadForVersion: "",
      lastAutoReloadAt: 0
    });

    await safeStorageSet({
      updateAvailable: false,
      lastKnownServerVersion: backendVer
    });

    const alreadyTriedSame = stored.lastAutoReloadForVersion === backendVer;
    const elapsed = Date.now() - Number(stored.lastAutoReloadAt || 0);
    if (!alreadyTriedSame && !syncReloadTriggered) {
      syncReloadTriggered = true;
      await safeStorageSet({
        lastAutoReloadForVersion: backendVer,
        lastAutoReloadAt: Date.now(),
        updateAvailable: false
      });
      if (updateBanner) updateBanner.style.display = 'block';
      if (updateBannerText) {
        updateBannerText.innerHTML = `Syncing to v<strong>${backendVer}</strong>...`;
      }
      if (updateStatus) {
        updateStatus.style.display = 'block';
        updateStatus.style.color = '#58a6ff';
        updateStatus.textContent = `Syncing to v${backendVer}...`;
      }
      if (btnUpdateNow) {
        btnUpdateNow.disabled = true;
        btnUpdateNow.textContent = "Syncing...";
      }
      setTimeout(() => {
        safeRuntimeReload();
        try { window.close(); } catch (_) {}
      }, 320);
      return true;
    }

    // Anti-loop fallback pill (if already attempted reload for this version or elapsed < 30s)
    if (elapsed >= 0 && updateBanner && btnUpdateNow) {
      updateBanner.style.display = 'block';
      if (updateBannerText) {
        updateBannerText.innerHTML = `Backend on v<strong id="update-version">${backendVer}</strong>`;
      }
      btnUpdateNow.disabled = false;
      btnUpdateNow.dataset.actionMode = "reload-extension";
      btnUpdateNow.textContent = "Reload extension";
    }
    return false;
  }

  // 1. Load Settings
  safeStorageGet({
    enabled: true,
    addCleanSuffix: false,
    projectZipToFolder: true,
    upscaleMode: 'off',
    autoFlowMode: 'off',
    updateAvailable: false,
    remoteVersion: ''
  }).then((items) => {
    const isEnabled = items.enabled !== false;
    toggleEnabled.checked = isEnabled;
    toggleSuffix.checked = !!items.addCleanSuffix;
    if (toggleProjectZip) toggleProjectZip.checked = items.projectZipToFolder !== false;
    selectUpscale.value = items.upscaleMode || 'off';
    if (selectAutoflow) selectAutoflow.value = items.autoFlowMode || 'off';
    updateToggleUI(isEnabled);

    if (updateBanner && items.updateAvailable) {
      const cleanVer = normalizeSemver(items.remoteVersion) || getManifestVersion();
      if (compareSemver(cleanVer, getManifestVersion()) > 0) {
        updateBanner.style.display = 'block';
        if (updateBannerText) {
          updateBannerText.innerHTML = `v<strong id="update-version">${cleanVer}</strong> ready`;
        } else if (updateVersion) {
          updateVersion.textContent = cleanVer;
        }
      }
    }
  }).catch(() => {});

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
    safeStorageSet({ enabled: isEnabled });

    if (isEnabled) {
      triggerManualWake(false);
    } else {
      safeRuntimeSendMessage({ type: "TOGGLE_ENABLED", enabled: false }, () => {
        checkHealth();
      });
    }
  });

  toggleSuffix.addEventListener('change', () => {
    safeStorageSet({ addCleanSuffix: toggleSuffix.checked });
  });

  if (toggleProjectZip) {
    toggleProjectZip.addEventListener('change', () => {
      safeStorageSet({ projectZipToFolder: toggleProjectZip.checked });
    });
  }

  selectUpscale.addEventListener('change', () => {
    safeStorageSet({ upscaleMode: selectUpscale.value });
  });

  if (selectAutoflow) {
    selectAutoflow.addEventListener('change', () => {
      safeStorageSet({ autoFlowMode: selectAutoflow.value });
    });
  }

  function clearWakeTimers() {
    if (wakeWatchdogTimer) {
      clearTimeout(wakeWatchdogTimer);
      wakeWatchdogTimer = null;
    }
    if (wakeFastPollTimer) {
      clearInterval(wakeFastPollTimer);
      wakeFastPollTimer = null;
    }
  }

  function showRetryHint(message = "Wake timed out — click Standby · Wake to retry") {
    if (retryHintTimer) clearTimeout(retryHintTimer);
    if (wakeRetryHint) {
      wakeRetryHint.textContent = message;
      wakeRetryHint.style.display = 'block';
      retryHintTimer = setTimeout(() => {
        wakeRetryHint.style.display = 'none';
      }, 4500);
    }
    hwPill.title = message;
  }

  function hideRetryHint() {
    if (retryHintTimer) {
      clearTimeout(retryHintTimer);
      retryHintTimer = null;
    }
    if (wakeRetryHint) wakeRetryHint.style.display = 'none';
    hwPill.title = "Click to wake server if standby";
  }

  function setOnlineUI(data) {
    clearWakeTimers();
    isStarting = false;
    hideRetryHint();
    statusDot.className = 'status-dot online';
    if (data && data.cuda_available) {
      const shortGpu = (data.gpu_name || 'GPU')
        .replace(/NVIDIA /i, '')
        .replace(/GeForce /i, '')
        .replace(/Laptop GPU/i, '')
        .trim();
      hwLabel.textContent = shortGpu || 'RTX GPU';
    } else if (data && data.mps_available) {
      hwLabel.textContent = 'Apple MPS';
    } else {
      hwLabel.textContent = 'CPU';
    }
    if (data && data.version && versionBadge) {
      const cleanBackend = normalizeSemver(data.version);
      const manifestVer = getManifestVersion();
      if (cleanBackend === manifestVer) {
        versionBadge.title = `Server: v${cleanBackend} (verified in sync)`;
      } else {
        versionBadge.title = `Server: v${cleanBackend} (Extension: v${manifestVer})`;
        syncProfileIfBackendNewer(cleanBackend).catch(() => {});
      }
    }
  }

  function setStartingUI() {
    isStarting = true;
    hideRetryHint();
    statusDot.className = 'status-dot starting';
    hwLabel.textContent = "Waking...";
  }

  async function probeHealth(timeoutMs = 1200) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const resp = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
      if (!resp.ok) return null;
      return await resp.json().catch(() => ({ status: "ONLINE" }));
    } catch (_) {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  async function finishWakeFailureWithRecheck() {
    const recheck = await probeHealth(1200);
    if (recheck) {
      setOnlineUI(recheck);
      return true;
    }
    clearWakeTimers();
    isStarting = false;
    statusDot.className = 'status-dot offline';
    hwLabel.textContent = 'Standby · Wake';
    showRetryHint();
    return false;
  }

  async function triggerManualWake(fromPillClick = true) {
    if (isStarting) return;

    const preData = await probeHealth(1200);
    if (preData) {
      setOnlineUI(preData);
      if (!fromPillClick) {
        safeRuntimeSendMessage({ type: "TOGGLE_ENABLED", enabled: true }, () => {});
      }
      return;
    }

    setStartingUI();

    wakeFastPollTimer = setInterval(() => {
      checkHealth();
    }, 350);

    wakeWatchdogTimer = setTimeout(() => {
      if (isStarting) {
        finishWakeFailureWithRecheck();
      }
    }, 15000);

    const msgPayload = fromPillClick
      ? { type: "ENSURE_SERVER_ONLINE" }
      : { type: "TOGGLE_ENABLED", enabled: true };

    safeRuntimeSendMessage(msgPayload, async (res, rtErr) => {
      if (!isStarting) return;

      if (rtErr) {
        await finishWakeFailureWithRecheck();
        return;
      }

      const online = fromPillClick ? (res && res.online) : (res && res.server && res.server.online);
      if (online) {
        const data = (res && res.data) || (res && res.server && res.server.data);
        if (data) {
          setOnlineUI(data);
        } else {
          await checkHealth();
        }
      } else {
        await finishWakeFailureWithRecheck();
      }
    });
  }

  // Header pill click to wake server manually (silently, zero black console, zero surprise browser tabs)
  hwPill.addEventListener('click', () => {
    if (!statusDot.classList.contains('online') && !isStarting) {
      triggerManualWake(true);
    }
  });

  // Batch Studio Button: ensure server online first, wait for 200 OK, then open tab
  btnOpenStudio.addEventListener('click', async () => {
    btnOpenStudio.disabled = true;
    const originalText = btnOpenStudio.textContent;
    btnOpenStudio.textContent = "Starting...";

    try {
      const bootRes = await new Promise((resolve) => {
        safeRuntimeSendMessage({ type: "ENSURE_SERVER_ONLINE" }, resolve);
      });

      if (bootRes && bootRes.online) {
        if (hasValidRuntime() && chrome.tabs) chrome.tabs.create({ url: API_BASE });
      } else {
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
          if (hasValidRuntime() && chrome.tabs) chrome.tabs.create({ url: API_BASE });
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

  // Update Now Handler (HTTP-First Self-Updater -> Standby Wake -> Native Host Fallback + Single-Flight Lock Support)
  if (btnUpdateNow) {
    btnUpdateNow.addEventListener('click', async () => {
      if (btnUpdateNow.dataset.actionMode === "reload-extension") {
        safeRuntimeReload();
        try { window.close(); } catch (_) {}
        return;
      }

      hideRetryHint();
      btnUpdateNow.disabled = true;
      btnUpdateNow.textContent = "Updating...";
      if (updateStatus) {
        updateStatus.className = 'update-status';
        updateStatus.style.display = 'block';
        updateStatus.textContent = "Checking local engine...";
        updateStatus.style.color = '#58a6ff';
      }

      const setProgressMsg = (msg) => {
        if (updateStatus) {
          updateStatus.style.display = 'block';
          updateStatus.style.color = '#58a6ff';
          updateStatus.textContent = msg;
        }
      };

      const finishUpdateSuccess = (verStr) => {
        const cleanVer = normalizeSemver(verStr) || getManifestVersion();
        safeStorageSet({
          updateAvailable: false,
          lastKnownServerVersion: cleanVer,
          lastAutoReloadForVersion: cleanVer,
          lastAutoReloadAt: Date.now()
        });
        hideRetryHint();
        if (updateStatus) {
          updateStatus.style.display = 'block';
          updateStatus.textContent = `Updated to v${cleanVer}! Reloading...`;
          updateStatus.style.color = '#238636';
        }
        setTimeout(() => {
          safeRuntimeReload();
          try { window.close(); } catch (_) {}
        }, 1100);
      };

      const failUpdateUI = (errMsg) => {
        if (updateStatus) {
          updateStatus.style.display = 'block';
          updateStatus.textContent = `Failed: ${errMsg}`;
          updateStatus.style.color = '#da3633';
        }
        btnUpdateNow.disabled = false;
        btnUpdateNow.textContent = "Retry";
      };

      const pollServerRestart = async (targetVer, assumeStarted = false, maxMs = 65000) => {
        let sawRestart = assumeStarted;
        const deadline = Date.now() + maxMs;
        while (Date.now() < deadline) {
          await new Promise(r => setTimeout(r, 600));
          const h = await probeHealth(900);
          if (!h) {
            sawRestart = true;
            setProgressMsg("Restarting FlowStudio engine...");
            continue;
          }
          const liveVer = normalizeSemver(h.version);
          if ((targetVer && compareSemver(liveVer, targetVer) >= 0) || (sawRestart && compareSemver(liveVer, getManifestVersion()) > 0)) {
            return { ok: true, version: liveVer || targetVer || getManifestVersion() };
          }
        }
        return { ok: false };
      };

      const tryHttpUpdate = async (targetVer) => {
        const res = await fetch(`${API_BASE}/api/system/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
          signal: AbortSignal.timeout(4000)
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) {
          return { fatal: true, error: data.detail || "Developer safety guard refused self-update." };
        }
        if (res.ok && data && data.ok) {
          const isConcurrent = data.status === "already_updating";
          setProgressMsg(isConcurrent ? "Update already running in another profile..." : "Updating files & repairing Native Host...");
          const restarted = await pollServerRestart(targetVer, isConcurrent, 65000);
          if (restarted.ok) {
            return { ok: true, version: restarted.version };
          }
          return { fatal: true, error: "Update triggered, server restart timed out after 65s." };
        }
        return { fatal: true, error: data.detail || `Update error (HTTP ${res.status})` };
      };

      const storedInfo = await safeStorageGet({ remoteVersion: '' });
      const targetVer = normalizeSemver(storedInfo.remoteVersion);

      let healthNow = await probeHealth(900);
      if (healthNow && compareSemver(healthNow.version, getManifestVersion()) > 0) {
        await syncProfileIfBackendNewer(healthNow.version);
        return;
      }

      if (!healthNow) {
        setProgressMsg("Server in standby - waking local updater...");
        const wakeRes = await new Promise((resolve) => {
          safeRuntimeSendMessage({ type: "ENSURE_SERVER_ONLINE", maxWaitMs: 8000 }, (r) => {
            resolve(r || { online: false });
          });
        });
        if (wakeRes && wakeRes.online) {
          healthNow = wakeRes.data || await probeHealth(1000);
          if (healthNow && compareSemver(healthNow.version, getManifestVersion()) > 0) {
            await syncProfileIfBackendNewer(healthNow.version);
            return;
          }
        }
      }

      if (healthNow) {
        try {
          setProgressMsg("Starting HTTP self-update...");
          const httpOutcome = await tryHttpUpdate(targetVer);
          if (httpOutcome.ok) {
            finishUpdateSuccess(httpOutcome.version);
            return;
          }
          if (httpOutcome.fatal) {
            failUpdateUI(httpOutcome.error);
            return;
          }
        } catch (_) {}
      }

      setProgressMsg("Running Native Bridge self-updater...");
      safeRuntimeSendMessage({ type: "TRIGGER_UPDATE_NATIVE" }, async (res, rtErr) => {
        if (res && res.ok && res.status === "already_updating") {
          setProgressMsg("Update already running in another profile...");
          const restarted = await pollServerRestart(targetVer, true, 65000);
          if (restarted.ok) {
            finishUpdateSuccess(restarted.version);
          } else {
            failUpdateUI("Concurrent update timed out waiting for server restart.");
          }
          return;
        }
        if (res && res.ok) {
          const checkH = await probeHealth(1200);
          finishUpdateSuccess((checkH && checkH.version) || res.version || targetVer || getManifestVersion());
          return;
        }
        const hAfter = await probeHealth(1200);
        if (hAfter && targetVer && compareSemver(hAfter.version, targetVer) >= 0) {
          finishUpdateSuccess(hAfter.version);
          return;
        }
        const errMsg = (rtErr && rtErr.message) || (res && res.error) || "Update failed";
        failUpdateUI(errMsg);
      });
    });
  }

  // Check for updates button
  if (btnCheckUpdate) {
    btnCheckUpdate.addEventListener('click', async () => {
      btnCheckUpdate.style.transform = 'rotate(180deg)';
      setTimeout(() => { btnCheckUpdate.style.transform = ''; }, 400);

      try {
        const h = await probeHealth(800);
        if (h && h.version && compareSemver(h.version, getManifestVersion()) > 0) {
          await syncProfileIfBackendNewer(h.version);
          return;
        }

        const manifestVer = getManifestVersion();
        const { lastKnownServerVersion = manifestVer } = await safeStorageGet({ lastKnownServerVersion: manifestVer });
        const effectiveCurrent = compareSemver(lastKnownServerVersion, manifestVer) > 0
          ? normalizeSemver(lastKnownServerVersion)
          : manifestVer;

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
        if (remoteVer && compareSemver(remoteVer, effectiveCurrent) > 0) {
          safeStorageSet({
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
    const data = await probeHealth(1200);
    if (data) {
      setOnlineUI(data);
    } else {
      handleHealthFailure();
    }
  }

  function handleHealthFailure() {
    if (isStarting) {
      statusDot.className = 'status-dot starting';
      hwLabel.textContent = 'Waking...';
    } else {
      statusDot.className = 'status-dot offline';
      hwLabel.textContent = 'Standby · Wake';
    }
  }

  if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.onMessage && typeof chrome.runtime.onMessage.addListener === "function") {
    chrome.runtime.onMessage.addListener((msg) => {
      try {
        if (msg && (msg.type === "SERVER_STATUS_CHANGED" || msg.type === "SERVER_STATUS")) {
          if (msg.status === "online") {
            if (msg.data) {
              setOnlineUI(msg.data);
            } else {
              clearWakeTimers();
              isStarting = false;
              checkHealth();
            }
          } else if (msg.status === "starting") {
            if (!isStarting) setStartingUI();
          } else {
            clearWakeTimers();
            isStarting = false;
            handleHealthFailure();
          }
        }
      } catch (_) {}
    });
  }

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

    const hasFinished = jobs.some(j => ['completed', 'cancelled', 'failed'].includes(j.status));
    if (clearHistoryBtn) clearHistoryBtn.disabled = !hasFinished;

    let html = '';

    for (const j of jobs) {
      const isVid = j.file_type === 'video';
      const isProj = j.file_type === 'project';
      const tag = isProj ? (j.is_zip ? 'ZIP' : 'PROJ') : (isVid ? 'VID' : 'IMG');
      const tagClass = isProj ? 'job-tag project' : 'job-tag';
      const pct = Math.round(j.progress_pct || 0);

      let actionButtons = '';
      let bottomLine = '';

      if (j.status === 'processing') {
        actionButtons = `
          <button class="micro-btn pause" data-action="pause" data-id="${j.id}" title="Pause job">${SVG_PAUSE}</button>
          <button class="micro-btn cancel" data-action="cancel" data-id="${j.id}" title="Cancel job">${SVG_CANCEL}</button>
        `;
        let metaText = `${pct}%`;
        let metaTitle = '';
        if (isProj) {
          const doneFiles = j.current_frame || 0;
          const totFiles = j.total_frames || 0;
          const curFile = j.current_file || '';
          metaText = totFiles > 0 ? `${pct}% · ${doneFiles}/${totFiles}` : (curFile ? escapeHtml(curFile) : `${pct}%`);
          if (curFile) metaTitle = ` title="${escapeHtml(curFile)}"`;
        } else {
          const etaText = j.eta_sec ? ` · ${j.eta_sec}s` : '';
          metaText = `${pct}%${etaText}`;
        }
        bottomLine = `
          <div class="job-bottom">
            <div class="job-progress-bar"><div class="job-progress-fill" style="width: ${pct}%;"></div></div>
            <span class="job-progress-meta"${metaTitle}>${metaText}</span>
          </div>
        `;
      } else if (j.status === 'paused') {
        actionButtons = `
          <button class="micro-btn resume" data-action="resume" data-id="${j.id}" title="Resume job">${SVG_RESUME}</button>
          <button class="micro-btn cancel" data-action="cancel" data-id="${j.id}" title="Cancel job">${SVG_CANCEL}</button>
        `;
        const pauseMeta = (isProj && j.total_frames > 0)
          ? `Paused · ${j.current_frame || 0}/${j.total_frames}`
          : `Paused · ${pct}%`;
        bottomLine = `
          <div class="job-bottom">
            <div class="job-progress-bar"><div class="job-progress-fill paused" style="width: ${pct}%;"></div></div>
            <span class="job-progress-meta" style="color: #d29922;">${pauseMeta}</span>
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
        const revealPath = j.output_path || j.final_saved_path || '';
        const revealBtn = `<button class="micro-btn folder" data-action="reveal" data-id="${j.id}" data-path="${escapeHtml(revealPath)}" title="Show in folder" aria-label="Show in folder" ${revealPath ? '' : 'disabled'}>${SVG_FOLDER}</button>`;
        if (isProj) {
          const ps = j.project_summary || {};
          const cleaned = Number(ps.cleaned_count || 0);
          const savedPath = revealPath;
          const folderName = savedPath ? savedPath.split(/[\\/]/).filter(Boolean).pop() : '';
          const summaryTitle = savedPath ? `Saved to ${savedPath} (${cleaned} cleaned)` : `${cleaned} cleaned`;
          actionButtons = `
            <span class="badge-status success" title="${escapeHtml(summaryTitle)}">✓ ${cleaned} cleaned</span>
            ${revealBtn}
            <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
          `;
          if (folderName) {
            bottomLine = `
              <div class="job-bottom">
                <span class="job-progress-meta" title="${escapeHtml(savedPath)}">📁 ${escapeHtml(folderName)}</span>
              </div>
            `;
          }
        } else {
          const copyChip = j.copied_to_clipboard ? '<span class="chip-copied" title="Copied — Ctrl+V">📋</span>' : '';
          actionButtons = `
            <span class="badge-status success" title="${escapeHtml(revealPath || 'Completed')}">✓ ${copyChip}</span>
            ${revealBtn}
            <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
          `;
        }
      } else if (j.status === 'cancelled') {
        actionButtons = `
          <span class="badge-status muted">Cancelled</span>
          <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
        `;
      } else {
        actionButtons = `
          <span class="badge-status danger" title="${escapeHtml(j.error || 'Failed')}">Failed</span>
          <button class="micro-btn remove" data-action="delete" data-id="${j.id}" title="Remove">${SVG_REMOVE}</button>
        `;
      }

      html += `
        <div class="job-item" data-id="${j.id}">
          <div class="job-top">
            <div class="job-meta">
              <span class="${tagClass}">${tag}</span>
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

    const sig = jobs.map(j => [
      j.id,
      j.status,
      j.progress_pct,
      j.current_frame,
      j.total_frames,
      j.output_path,
      j.final_saved_path,
      j.copied_to_clipboard,
      (j.project_summary && j.project_summary.cleaned_count) || 0,
      j.error || ''
    ].join('|')).join(';');
    if (sig === lastJobsSignature) {
      return;
    }
    lastJobsSignature = sig;
    activityList.innerHTML = html;

    activityList.querySelectorAll('.micro-btn').forEach((btn) => {
      btn.onclick = async () => {
        const action = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id');

        if (action === 'reveal') {
          const targetPath = btn.getAttribute('data-path') || '';
          if (!targetPath) {
            showActivityToast('Output path is not available for this job.', true);
            return;
          }
          btn.disabled = true;
          try {
            const res = await fetch(`${API_BASE}/api/system/reveal-path`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ path: targetPath })
            });
            if (!res.ok) {
              const err = await res.json().catch(() => ({}));
              showActivityToast(err.detail || 'File or folder no longer exists on disk.', true);
            }
          } catch (_) {
            showActivityToast('FlowStudio backend offline — click Wake.', true);
          } finally {
            btn.disabled = false;
          }
          return;
        }

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
          lastJobsSignature = '';
          fetchRecentActivity();
        } catch (_) {
          btn.disabled = false;
        }
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

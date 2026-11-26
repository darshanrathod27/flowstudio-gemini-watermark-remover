// FlowStudio Pro - Background Service Worker (Manifest V3, v4.0.2)
const API_BASE = "http://127.0.0.1:8765";
const CLOUDFLARE_VERSION_URL = "https://flowstudio-api.flowstudio-app.workers.dev/api/version";
const GITHUB_VERSION_URL = "https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json";
const CURRENT_VERSION = "4.0.2";

const DEFAULT_SETTINGS = {
  enabled: true,
  addCleanSuffix: false,
  projectZipToFolder: true,
  upscaleMode: "off",
  autoFlowMode: "off",
  lastActiveTime: Date.now()
};

const MEDIA_EXTS = ['.mp4', '.mov', '.mkv', '.webm', '.jpg', '.jpeg', '.png', '.webp'];
const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];
const FLOW_DOMAINS = ['flow.google.com', 'labs.google', 'googleusercontent.com', 'storage.googleapis.com', 'aisandbox'];
const TEMP_SUFFIXES = ['.tmp', '.crdownload', '.part', '.partial'];

const activeZipDownloadIds = new Set();
const activeMediaDownloadIds = new Set();

function normalizeSemver(v) {
  return String(v || "0.0.0").trim().replace(/^v+/i, "");
}

function isNewerVersion(latest, current) {
  const l = normalizeSemver(latest).split(".").map(Number);
  const c = normalizeSemver(current).split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    const lv = l[i] || 0;
    const cv = c[i] || 0;
    if (lv > cv) return true;
    if (lv < cv) return false;
  }
  return false;
}

async function checkForUpdates() {
  try {
    let data = null;
    try {
      const cfRes = await fetch(CLOUDFLARE_VERSION_URL, { cache: "no-store", signal: AbortSignal.timeout(3000) });
      if (cfRes.ok) {
        data = await cfRes.json();
      }
    } catch (_) {
      // Cloudflare worker unreachable - fallback to GitHub raw
    }

    if (!data) {
      const ghRes = await fetch(GITHUB_VERSION_URL, { cache: "no-store", signal: AbortSignal.timeout(4000) });
      if (ghRes.ok) {
        data = await ghRes.json();
      }
    }

    if (data && data.version && isNewerVersion(data.version, CURRENT_VERSION)) {
      await chrome.storage.local.set({
        updateAvailable: true,
        remoteVersion: normalizeSemver(data.version),
        releaseUrl: data.releases_url || data.repo_url || "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover"
      });
      console.log(`[FlowStudio] Update available: v${normalizeSemver(data.version)}`);
    } else {
      await chrome.storage.local.set({ updateAvailable: false });
    }
  } catch (e) {
    // Offline or network error - ignore silently
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  const allExisting = await chrome.storage.local.get(null);
  const keepKeys = new Set([
    ...Object.keys(DEFAULT_SETTINGS),
    "trackedDownloadIds",
    "updateAvailable",
    "remoteVersion",
    "releaseUrl"
  ]);
  const obsoleteKeys = Object.keys(allExisting).filter(k => !keepKeys.has(k));
  if (obsoleteKeys.length > 0) {
    await chrome.storage.local.remove(obsoleteKeys);
  }

  const sanitizedExisting = {};
  for (const k of keepKeys) {
    if (Object.prototype.hasOwnProperty.call(allExisting, k)) {
      sanitizedExisting[k] = allExisting[k];
    }
  }
  const toSet = { ...DEFAULT_SETTINGS, ...sanitizedExisting, trackedDownloadIds: [] };
  await chrome.storage.local.set(toSet);
  console.log('[FlowStudio] Background Service Worker Initialized (Native Messaging Bridge v4.0.0).');

  // Alarms: 60-min self-heal, 24-hr update check (Zero surprise idle shutdown)
  chrome.alarms.create("flowstudio_self_heal", { periodInMinutes: 60 });
  chrome.alarms.create("checkUpdate", { periodInMinutes: 1440 });
  checkForUpdates();
});

chrome.runtime.onStartup.addListener(() => {
  checkForUpdates();
});

async function getSettings() {
  const data = await chrome.storage.local.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...data };
}

function sendNative(msg) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendNativeMessage("com.flowstudio.bridge", msg, (response) => {
        if (chrome.runtime.lastError) {
          const errMsg = chrome.runtime.lastError.message || "Native host communication error";
          console.warn("[FlowStudio Bridge] Native error:", errMsg);
          resolve({ ok: false, error: errMsg });
        } else {
          resolve(response || { ok: true });
        }
      });
    } catch (e) {
      console.warn("[FlowStudio Bridge] Exception:", e);
      resolve({ ok: false, error: e.message || String(e) });
    }
  });
}

function getCleanBasename(filePath, fallback = "flow_media.png") {
  if (!filePath) return fallback;
  let base = String(filePath).trim().replace(/\\/g, '/').split('/').pop() || '';
  if (/^[A-Za-z]:/.test(base)) {
    base = base.slice(2).replace(/^[\\/]+/, '');
  }
  return base || fallback;
}

function isTempOrPartialPath(filePath) {
  if (!filePath) return false;
  const lower = String(filePath).trim().toLowerCase();
  if (!lower) return false;
  if (TEMP_SUFFIXES.some(ext => lower.endsWith(ext))) return true;
  if (lower.includes('.flowtmp_') || lower.includes('.tmp_flowstudio')) return true;
  return false;
}

function isMediaFilename(filename) {
  if (!filename || isTempOrPartialPath(filename)) return false;
  const lower = getCleanBasename(filename, '').toLowerCase();
  return MEDIA_EXTS.some(ext => lower.endsWith(ext));
}

function isImageFilename(filename) {
  if (!filename || isTempOrPartialPath(filename)) return false;
  const lower = getCleanBasename(filename, '').toLowerCase();
  return IMAGE_EXTS.some(ext => lower.endsWith(ext));
}

function isZipFilename(filename) {
  if (!filename || isTempOrPartialPath(filename)) return false;
  const lower = getCleanBasename(filename, '').toLowerCase();
  return lower.endsWith('.zip');
}

function isStudioLoopUrl(rawUrl) {
  const lower = String(rawUrl || '').toLowerCase();
  return lower.startsWith(API_BASE.toLowerCase()) || lower.startsWith('http://localhost:8765');
}

function isAlreadyCleanedFilename(filename) {
  const base = getCleanBasename(filename, '');
  return /_clean(\s*\(\d+\))?\.[a-z0-9]+$/i.test(base) || base.toLowerCase().includes('flowstudio_batch_');
}

function matchesAllowedDomain(rawUrl, domains) {
  if (!rawUrl) return false;
  const lower = String(rawUrl).toLowerCase();
  let target = lower;
  if (target.startsWith('blob:')) {
    target = target.slice(5);
  }
  try {
    const host = new URL(target).hostname.toLowerCase();
    return domains.some(d => host === d || host.endsWith('.' + d));
  } catch (_) {
    return domains.some(d => lower.includes(d));
  }
}

async function isFlowRelatedDownload(item, includeActiveTab = true) {
  if (!item) return false;
  if (
    matchesAllowedDomain(item.url, FLOW_DOMAINS) ||
    matchesAllowedDomain(item.finalUrl, FLOW_DOMAINS) ||
    matchesAllowedDomain(item.referrer, FLOW_DOMAINS) ||
    String(item.url || '').toLowerCase().startsWith('blob:https://flow.google.com')
  ) {
    return true;
  }
  if (includeActiveTab) {
    try {
      const flowTabs = await chrome.tabs.query({ url: "*://flow.google.com/*" });
      if (flowTabs && flowTabs.length > 0) return true;
    } catch (_) {}
  }
  return false;
}

async function addTrackedDownloadId(id) {
  const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
  if (!trackedDownloadIds.includes(id)) {
    trackedDownloadIds.push(id);
    await chrome.storage.local.set({ trackedDownloadIds });
  }
}

async function removeTrackedDownloadId(id) {
  const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
  if (trackedDownloadIds.includes(id)) {
    await chrome.storage.local.set({ trackedDownloadIds: trackedDownloadIds.filter(x => x !== id) });
  }
}

async function handleCompletedZipDownload(dl, settings, wasTracked = false) {
  if (!dl || !dl.filename || !settings || !settings.enabled || !settings.projectZipToFolder) return;

  const filename = dl.filename;
  if (isTempOrPartialPath(filename) || !isZipFilename(filename)) return;

  if (isStudioLoopUrl(dl.url) || isStudioLoopUrl(dl.finalUrl) || isAlreadyCleanedFilename(filename)) {
    return;
  }

  const isFlowZip =
    wasTracked ||
    matchesAllowedDomain(dl.url, FLOW_DOMAINS) ||
    matchesAllowedDomain(dl.finalUrl, FLOW_DOMAINS) ||
    matchesAllowedDomain(dl.referrer, FLOW_DOMAINS) ||
    await isFlowRelatedDownload(dl, true);
  if (!isFlowZip) return;

  if (activeZipDownloadIds.has(dl.id)) return;
  activeZipDownloadIds.add(dl.id);

  try {
    await chrome.storage.local.set({ lastActiveTime: Date.now() });
    console.log(`[FlowStudio] Project ZIP detected from Flow (${dl.id}): ${filename}`);
    chrome.action.setBadgeText({ text: "..." });
    chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });

    const bootRes = await ensureServerOnline(22000);
    if (!bootRes.online) {
      console.error("[FlowStudio] Project ZIP ingest failed: server did not come online within timeout.");
      chrome.action.setBadgeText({ text: "!" });
      chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
      return;
    }

    const upscaleMode = settings.upscaleMode || "off";
    const isUpscaleOn = !["off", "none", ""].includes(String(upscaleMode).toLowerCase());
    const payload = {
      file_path: filename,
      output_name: "",
      upscale_mode: upscaleMode,
      upscale_clean_files: isUpscaleOn,
      delete_source_zip: true
    };

    let res = await fetch(`${API_BASE}/api/extension/ingest-zip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok && (res.status === 404 || res.status === 423 || res.status === 400)) {
      await new Promise(r => setTimeout(r, 450));
      res = await fetch(`${API_BASE}/api/extension/ingest-zip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    }

    const ingestData = await res.json().catch(() => ({}));
    if (res.ok && ingestData && (ingestData.ok || ingestData.job_id)) {
      await removeTrackedDownloadId(dl.id);
      chrome.downloads.erase({ id: dl.id }, () => {});
      chrome.action.setBadgeText({ text: "✓" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
    } else if (res.ok && ingestData && ingestData.status === "SKIPPED") {
      await removeTrackedDownloadId(dl.id);
      chrome.action.setBadgeText({ text: "" });
    } else {
      console.warn("[FlowStudio] Project ZIP ingest returned error:", res.status, ingestData);
      chrome.action.setBadgeText({ text: "!" });
      chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
    }
  } catch (err) {
    console.error("[FlowStudio] Project ZIP ingest error:", err);
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
  } finally {
    activeZipDownloadIds.delete(dl.id);
  }
}

// -------------------------------------------------------------
// Single-Flight Boot Manager (Zero Infinite Buffer Lock)
// -------------------------------------------------------------
let wakingPromise = null;

function broadcastServerStatus(status, data = null) {
  try {
    chrome.runtime.sendMessage({ type: "SERVER_STATUS_CHANGED", status, data }).catch(() => {});
  } catch (_) {}
  try {
    chrome.runtime.sendMessage({ type: "SERVER_STATUS", status, data }).catch(() => {});
  } catch (_) {}
}

async function fetchHealthWithTimeout(timeoutMs = 1200) {
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

function sendNativeWithTimeout(msg, timeoutMs = 13500) {
  return new Promise((resolve) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        resolve({ ok: false, timedOut: true, error: "Native wake timed out" });
      }
    }, timeoutMs);

    sendNative(msg).then((res) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        resolve(res);
      }
    });
  });
}

function ensureServerOnline(maxWaitMs = 15000) {
  if (wakingPromise) return wakingPromise;

  const hardCapMs = Math.min(Math.max(1000, Number(maxWaitMs) || 15000), 15000);

  wakingPromise = (async () => {
    const initialData = await fetchHealthWithTimeout(1200);
    if (initialData) {
      broadcastServerStatus("online", initialData);
      return { online: true, data: initialData };
    }

    console.log("[FlowStudio] Server offline. Firing non-blocking native bridge wake...");
    broadcastServerStatus("starting");
    const nativePromise = sendNativeWithTimeout({ cmd: "start" }, Math.max(4000, hardCapMs - 1000));
    let nativeDone = false;
    let nativeRes = null;
    nativePromise.then((res) => {
      nativeDone = true;
      nativeRes = res;
    });

    const deadline = Date.now() + hardCapMs;
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 250));
      const data = await fetchHealthWithTimeout(900);
      if (data) {
        broadcastServerStatus("online", data);
        return { online: true, data };
      }

      if (nativeDone && nativeRes && !nativeRes.ok && !nativeRes.timedOut) {
        const recheckData = await fetchHealthWithTimeout(1200);
        if (recheckData) {
          broadcastServerStatus("online", recheckData);
          return { online: true, data: recheckData };
        }
        break;
      }
    }

    const finalCheck = await fetchHealthWithTimeout(1200);
    if (finalCheck) {
      broadcastServerStatus("online", finalCheck);
      return { online: true, data: finalCheck };
    }

    broadcastServerStatus("offline");
    return {
      online: false,
      error: (nativeRes && nativeRes.error) || "Server did not respond within 15s"
    };
  })().finally(() => {
    wakingPromise = null;
  });

  return wakingPromise;
}

// -------------------------------------------------------------
// Auto-Add Image to Flow (Project Drop vs Chat Paste)
// -------------------------------------------------------------
async function sendImageToFlow(jobId, filename) {
  try {
    const { autoFlowMode = "off" } = await chrome.storage.local.get({ autoFlowMode: "off" });
    if (!autoFlowMode || autoFlowMode === "off") return;

    const cleanName = getCleanBasename(filename, "clean_image.png");
    if (!isImageFilename(cleanName)) return;

    let base64 = null;
    let mimeType = "image/png";

    try {
      const b64Res = await fetch(`${API_BASE}/api/jobs/${jobId}/file-base64`);
      if (b64Res.ok) {
        const b64Data = await b64Res.json();
        base64 = b64Data.data_base64;
        mimeType = b64Data.mime || "image/png";
      }
    } catch (_) {}

    if (!base64) {
      const dlRes = await fetch(`${API_BASE}/api/jobs/${jobId}/download`);
      if (dlRes.ok) {
        const blob = await dlRes.blob();
        if (blob.size > 25 * 1024 * 1024) return;
        mimeType = blob.type || "image/png";
        base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onloadend = () => {
            const res = reader.result;
            const b64 = (res && res.split(',')[1]) || res;
            resolve(b64);
          };
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      }
    }

    if (!base64) return;

    const tabs = await chrome.tabs.query({ url: "*://flow.google.com/*" });
    if (!tabs || tabs.length === 0) return;

    const targetTab = tabs.find(t => t.active) || tabs[0];
    const payload = {
      type: "FLOW_ATTACH_IMAGE",
      mode: autoFlowMode,
      base64,
      mimeType,
      filename: cleanName
    };

    try {
      const reply = await chrome.tabs.sendMessage(targetTab.id, payload);
      if (reply && reply.ok) {
        console.log(`[FlowStudio] Image attached to Flow via ${reply.method}`);
        return;
      }
    } catch (_) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: targetTab.id },
          files: ["content_flow.js"]
        });
        await new Promise(r => setTimeout(r, 120));
        await chrome.tabs.sendMessage(targetTab.id, payload);
        console.log(`[FlowStudio] Image attached to Flow after injecting content_flow.js`);
      } catch (e) {
        console.warn("[FlowStudio] Failed to send image to Flow tab:", e);
      }
    }
  } catch (err) {
    console.warn("[FlowStudio] sendImageToFlow error:", err);
  }
}

async function triggerHttpFirstUpdate(targetVersion = "") {
  try {
    const updRes = await fetch(`${API_BASE}/api/system/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: AbortSignal.timeout(4000)
    });
    const updData = await updRes.json().catch(() => ({}));
    if (updRes.status === 403) {
      return { ok: false, error: updData.detail || "Developer safety guard blocked update" };
    }
    if (updRes.ok && updData && updData.ok) {
      let sawRestart = false;
      const deadline = Date.now() + 65000;
      const cleanTarget = normalizeSemver(targetVersion);
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 600));
        const h = await fetchHealthWithTimeout(900);
        if (!h) {
          sawRestart = true;
          continue;
        }
        const liveVer = normalizeSemver(h.version);
        if (cleanTarget && liveVer === cleanTarget && sawRestart) {
          return { ok: true, method: "http", version: liveVer };
        }
        if (sawRestart) {
          return { ok: true, method: "http", version: liveVer || cleanTarget || CURRENT_VERSION };
        }
      }
      return { ok: false, error: "Update started in background but server timed out restarting" };
    }
  } catch (_) {
    // HTTP server offline or restarting - fall through to Native Messaging fallback
  }
  return await sendNative({ cmd: "update" });
}

// Message Listener from Popup or Tabs
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const cmd = request.cmd || request.action;
  if (request.type === "TRIGGER_UPDATE_NATIVE") {
    sendNative({ cmd: "update" }).then((res) => {
      sendResponse(res);
    });
    return true;
  }
  if (request.type === "TRIGGER_UPDATE" || cmd === "update") {
    triggerHttpFirstUpdate(request.targetVersion || "").then((res) => {
      sendResponse(res);
    });
    return true;
  }
  if (request.type === "ENSURE_SERVER_ONLINE" || cmd === "ensure_online") {
    ensureServerOnline(request.maxWaitMs || 15000).then((res) => {
      sendResponse(res);
    });
    return true;
  }
  if (request.type === "TOGGLE_ENABLED") {
    const isEnabled = !!request.enabled;
    chrome.storage.local.set({ enabled: isEnabled }).then(() => {
      if (isEnabled) {
        ensureServerOnline().then((res) => sendResponse({ ok: true, server: res }));
      } else {
        // STRICT SAFETY: Toggling OFF ONLY pauses interception. NEVER send stop command!
        sendResponse({ ok: true });
      }
    });
    return true;
  }
  if (cmd === "start") {
    ensureServerOnline().then((res) => sendResponse(res));
    return true;
  }
  if (cmd === "status" || cmd === "ping") {
    sendNative({ cmd }).then((res) => {
      sendResponse(res);
    });
    return true;
  }
});

// 1. Periodic 60-Minute Self-Heal Alarm (Zero Auto-Wake, Zero Idle Shutdown)
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "flowstudio_self_heal") {
    try {
      console.log("[FlowStudio] 60-Minute self-heal check running...");
      const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
      if (trackedDownloadIds.length > 0) {
        const validIds = [];
        for (const id of trackedDownloadIds) {
          try {
            const [d] = await chrome.downloads.search({ id });
            if (d && (d.state === "in_progress" || d.state === "complete")) {
              validIds.push(id);
            }
          } catch (_) {}
        }
        await chrome.storage.local.set({ trackedDownloadIds: validIds });
      }
    } catch (err) {
      console.warn("[FlowStudio Self-Heal] Error:", err);
    }
  } else if (alarm.name === "checkUpdate") {
    checkForUpdates();
  }
});

// 2. Zero-Bypass, Zero-.TMP Download Tracking (onCreated + onDeterminingFilename + onChanged)
// Note: Chrome creates <UUID>.tmp during transfer and removes/renames it itself upon completion.
// Never call chrome.downloads.cancel() mid-transfer on Windows NTFS; ingest cleanly once state === "complete"!
chrome.downloads.onCreated.addListener(async (item) => {
  try {
    const settings = await getSettings();
    if (!settings.enabled) return;

    const filename = item.filename || '';
    if (isStudioLoopUrl(item.url) || isTempOrPartialPath(filename) || isAlreadyCleanedFilename(filename)) return;

    const mimeStr = String(item.mime || '').toLowerCase();
    const looksMedia = mimeStr.startsWith('video/') || mimeStr.startsWith('image/') || isMediaFilename(filename);
    const looksZip = mimeStr.includes('zip') || isZipFilename(filename);
    const pendingNameAndMime = !filename && (!mimeStr || mimeStr === 'application/octet-stream');

    if (!looksMedia && !looksZip && !pendingNameAndMime) return;

    const isFlow = await isFlowRelatedDownload(item, true);
    if (!isFlow) return;

    await chrome.storage.local.set({ lastActiveTime: Date.now() });
    await addTrackedDownloadId(item.id);
    ensureServerOnline();
  } catch (err) {
    console.warn('[FlowStudio] onCreated error:', err);
  }
});

chrome.downloads.onDeterminingFilename.addListener((item) => {
  try {
    if (!item || isTempOrPartialPath(item.filename)) return;
    if (isStudioLoopUrl(item.url) || isStudioLoopUrl(item.finalUrl) || isAlreadyCleanedFilename(item.filename)) {
      removeTrackedDownloadId(item.id);
      return;
    }

    const mimeStr = String(item.mime || '').toLowerCase();
    const isMediaOrZip =
      mimeStr.startsWith('video/') ||
      mimeStr.startsWith('image/') ||
      isMediaFilename(item.filename) ||
      mimeStr.includes('zip') ||
      isZipFilename(item.filename);

    if (!isMediaOrZip) {
      removeTrackedDownloadId(item.id);
      return;
    }

    isFlowRelatedDownload(item, true).then((isFlow) => {
      if (isFlow) {
        addTrackedDownloadId(item.id);
      }
    });
  } catch (err) {
    console.warn('[FlowStudio] onDeterminingFilename error:', err);
  }
});

// Clean ingestion strictly on state === "complete" (0 orphan <UUID>.TMP files!)
chrome.downloads.onChanged.addListener(async (delta) => {
  if (delta.state && delta.state.current === 'interrupted') {
    await removeTrackedDownloadId(delta.id);
    activeZipDownloadIds.delete(delta.id);
    activeMediaDownloadIds.delete(delta.id);
    return;
  }

  if (!delta.state || delta.state.current !== 'complete') return;

  try {
    const settings = await getSettings();
    if (!settings.enabled) return;

    const [dl] = await chrome.downloads.search({ id: delta.id });
    if (!dl || dl.state !== 'complete' || !dl.filename || isTempOrPartialPath(dl.filename)) {
      return;
    }

    const filename = dl.filename;
    if (isStudioLoopUrl(dl.url) || isStudioLoopUrl(dl.finalUrl) || isAlreadyCleanedFilename(filename)) {
      await removeTrackedDownloadId(delta.id);
      return;
    }

    const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    const wasTracked = trackedDownloadIds.includes(delta.id);

    if (isZipFilename(filename)) {
      await handleCompletedZipDownload(dl, settings, wasTracked);
      return;
    }

    const mimeStr = String(dl.mime || '').toLowerCase();
    const isMedia = mimeStr.startsWith('video/') || mimeStr.startsWith('image/') || isMediaFilename(filename);
    if (!isMedia) {
      await removeTrackedDownloadId(delta.id);
      return;
    }

    const isFlow = wasTracked || await isFlowRelatedDownload(dl, true);
    if (!isFlow) return;

    if (activeMediaDownloadIds.has(dl.id)) return;
    activeMediaDownloadIds.add(dl.id);

    try {
      const bootRes = await ensureServerOnline(22000);
      if (!bootRes.online) {
        console.error("[FlowStudio] Ingest failed: server did not come online within timeout.");
        return;
      }

      const cleanLeafName = getCleanBasename(filename, 'flow_media.png');
      console.log(`[FlowStudio] Ingesting completed Flow media: ${filename}`);
      chrome.action.setBadgeText({ text: "..." });
      chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });

      const ingestPayload = {
        file_path: filename,
        upscale_mode: settings.upscaleMode || "off",
        remove_logo: true,
        add_clean_suffix: !!settings.addCleanSuffix,
        copy_image_to_clipboard: true
      };

      let res = await fetch(`${API_BASE}/api/extension/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ingestPayload)
      });

      if (!res.ok && (res.status === 404 || res.status === 423)) {
        await new Promise(r => setTimeout(r, 450));
        res = await fetch(`${API_BASE}/api/extension/ingest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(ingestPayload)
        });
      }

      if (res.ok) {
        const ingestData = await res.json().catch(() => ({}));
        await removeTrackedDownloadId(delta.id);
        chrome.downloads.erase({ id: delta.id }, () => {});
        if (ingestData && ingestData.status === "SKIPPED") {
          chrome.action.setBadgeText({ text: "" });
        } else {
          chrome.action.setBadgeText({ text: "✓" });
          chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
          setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
        }

        if (ingestData && ingestData.job_id && isImageFilename(cleanLeafName)) {
          (async () => {
            const jobId = ingestData.job_id;
            for (let i = 0; i < 60; i++) {
              await new Promise(r => setTimeout(r, 500));
              try {
                const jResp = await fetch(`${API_BASE}/api/jobs/${jobId}`);
                if (jResp.ok) {
                  const jData = await jResp.json();
                  if (jData.status === "completed") {
                    sendImageToFlow(jobId, cleanLeafName);
                    break;
                  } else if (jData.status === "failed" || jData.status === "cancelled") {
                    break;
                  }
                }
              } catch (_) {}
            }
          })();
        }
      } else {
        await removeTrackedDownloadId(delta.id);
        chrome.action.setBadgeText({ text: "!" });
        chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
        setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
      }
    } finally {
      activeMediaDownloadIds.delete(dl.id);
    }
  } catch (err) {
    console.error('[FlowStudio] onChanged ingest failed:', err);
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
  }
});

// FlowStudio Pro - Background Service Worker (Manifest V3, v3.9.0)
const API_BASE = "http://127.0.0.1:8765";
const CLOUDFLARE_VERSION_URL = "https://flowstudio-api.flowstudio-app.workers.dev/api/version";
const GITHUB_VERSION_URL = "https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json";
const CURRENT_VERSION = "3.9.0";

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
const ZIP_FLOW_DOMAINS = ['flow.google.com', 'googleusercontent.com', 'storage.googleapis.com'];
const activeZipDownloadIds = new Set();

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
  console.log('[FlowStudio] Background Service Worker Initialized (Native Messaging Bridge v3.9.0).');

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

function isMediaFilename(filename) {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return MEDIA_EXTS.some(ext => lower.endsWith(ext));
}

function isImageFilename(filename) {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return IMAGE_EXTS.some(ext => lower.endsWith(ext));
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

async function handleCompletedZipDownload(dl, settings) {
  if (!dl || !dl.filename || !settings || !settings.enabled || !settings.projectZipToFolder) return;

  const urlStr = (dl.url || '').toLowerCase();
  const finalUrlStr = (dl.finalUrl || '').toLowerCase();
  const filename = dl.filename;
  const lowerName = filename.toLowerCase();

  // Loop Prevention - ignore Studio exports and temp archives
  if (
    urlStr.startsWith(API_BASE.toLowerCase()) ||
    urlStr.startsWith('http://localhost:8765') ||
    finalUrlStr.startsWith(API_BASE.toLowerCase()) ||
    finalUrlStr.startsWith('http://localhost:8765')
  ) {
    return;
  }
  if (lowerName.includes('.flowtmp_') || lowerName.includes('.tmp_flowstudio') || lowerName.includes('flowstudio_batch_')) {
    return;
  }

  const isFlowZip =
    matchesAllowedDomain(dl.url, ZIP_FLOW_DOMAINS) ||
    matchesAllowedDomain(dl.finalUrl, ZIP_FLOW_DOMAINS) ||
    matchesAllowedDomain(dl.referrer, ZIP_FLOW_DOMAINS);
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

    // Brief retry in case Chrome/Defender has a transient lock right on completion
    if (!res.ok && (res.status === 404 || res.status === 400)) {
      await new Promise(r => setTimeout(r, 400));
      res = await fetch(`${API_BASE}/api/extension/ingest-zip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    }

    const ingestData = await res.json().catch(() => ({}));
    if (res.ok && ingestData && (ingestData.ok || ingestData.job_id)) {
      chrome.downloads.erase({ id: dl.id }, () => {});
      chrome.action.setBadgeText({ text: "✓" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
    } else if (res.ok && ingestData && ingestData.status === "SKIPPED") {
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

async function isServerOnline(timeoutMs = 1200) {
  const data = await fetchHealthWithTimeout(timeoutMs);
  return !!data;
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
    // 1. Immediate pre-check before spawning native host
    const initialData = await fetchHealthWithTimeout(1200);
    if (initialData) {
      broadcastServerStatus("online", initialData);
      return { online: true, data: initialData };
    }

    // 2. Broadcast waking & launch native host WITHOUT blocking the health poller
    console.log("[FlowStudio] Server offline. Firing non-blocking native bridge wake...");
    broadcastServerStatus("starting");
    const nativePromise = sendNativeWithTimeout({ cmd: "start" }, Math.max(4000, hardCapMs - 1000));
    let nativeDone = false;
    let nativeRes = null;
    nativePromise.then((res) => {
      nativeDone = true;
      nativeRes = res;
    });

    // 3. Fast concurrent 250ms health polling up to hard 15s cap
    const deadline = Date.now() + hardCapMs;
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 250));
      const data = await fetchHealthWithTimeout(900);
      if (data) {
        broadcastServerStatus("online", data);
        return { online: true, data };
      }

      // If native host failed early, still do 1 clean health re-check before exiting
      if (nativeDone && nativeRes && !nativeRes.ok && !nativeRes.timedOut) {
        const recheckData = await fetchHealthWithTimeout(1200);
        if (recheckData) {
          broadcastServerStatus("online", recheckData);
          return { online: true, data: recheckData };
        }
        break;
      }
    }

    // 4. Final clean health re-check before resetting to Standby
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

    if (!isImageFilename(filename)) return;

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
        if (blob.size > 25 * 1024 * 1024) return; // Guard <= 25MB
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
      filename: filename || "clean_image.png"
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

// Message Listener from Popup or Tabs
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const cmd = request.cmd || request.action;
  if (request.type === "TRIGGER_UPDATE" || cmd === "update") {
    sendNative({ cmd: "update" }).then((res) => {
      sendResponse(res);
    });
    return true;
  }
  if (request.type === "ENSURE_SERVER_ONLINE" || cmd === "ensure_online") {
    ensureServerOnline().then((res) => {
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

// 2. Bulletproof Zero-Bypass Download Interception: Path A (Direct URL) & Path B (Fallback / Ingestion)
chrome.downloads.onCreated.addListener(async (item) => {
  try {
    const settings = await getSettings();
    if (!settings.enabled) return;

    const urlStr = (item.url || '').toLowerCase();
    const refStr = (item.referrer || '').toLowerCase();
    const filename = item.filename || '';

    // Loop Prevention - ignore studio and already cleaned files
    if (urlStr.startsWith(API_BASE.toLowerCase()) || urlStr.startsWith('http://localhost:8765')) return;
    if (/_clean(\s*\(\d+\))?\.[a-z0-9]+$/i.test(filename) || filename.toLowerCase().includes('.flowtmp_')) return;

    const isMedia = (item.mime && (item.mime.startsWith('video/') || item.mime.startsWith('image/'))) || isMediaFilename(filename);
    if (!isMedia) return;

    const flowDomains = ['flow.google.com', 'labs.google', 'googleusercontent.com', 'storage.googleapis.com', 'aisandbox'];
    let isFlow = flowDomains.some(d => urlStr.includes(d) || refStr.includes(d)) || urlStr.startsWith('blob:https://flow.google.com');

    if (!isFlow) {
      const flowTabs = await chrome.tabs.query({ url: "*://flow.google.com/*" });
      if (flowTabs && flowTabs.length > 0) isFlow = true;
    }

    if (!isFlow) return;

    await chrome.storage.local.set({ lastActiveTime: Date.now() });

    // STEP 1: Persist item.id in trackedDownloadIds
    const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    if (!trackedDownloadIds.includes(item.id)) {
      trackedDownloadIds.push(item.id);
      await chrome.storage.local.set({ trackedDownloadIds });
    }

    // STEP 2: Check server health, wake server if needed
    const online = await isServerOnline(1200);
    if (!online && settings.enabled) {
      console.log("[FlowStudio] Server offline during download, firing ensureServerOnline...");
      ensureServerOnline();
    }

    // STEP 3 (PATH A — Direct Clean Fetch):
    if (online && item.url && item.url.startsWith('https://') && !item.url.startsWith('blob:')) {
      console.log(`[FlowStudio] PATH A: Intercepting direct Flow download URL #${item.id}: ${item.url}`);
      chrome.action.setBadgeText({ text: "..." });
      chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });

      const payload = {
        url: item.url,
        filename: item.filename || null,
        upscale_mode: settings.upscaleMode || "off",
        add_clean_suffix: !!settings.addCleanSuffix,
        save_dir: "downloads"
      };

      try {
        const resp = await fetch(`${API_BASE}/api/extension/fetch-and-clean`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (resp.ok) {
          const respData = await resp.json().catch(() => ({}));
          const { trackedDownloadIds: cur = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
          await chrome.storage.local.set({ trackedDownloadIds: cur.filter(x => x !== item.id) });
          chrome.downloads.cancel(item.id, () => {
            chrome.downloads.erase({ id: item.id }, () => {});
          });
          chrome.action.setBadgeText({ text: "✓" });
          chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
          setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);

          // Auto-Add to Flow trigger if image
          if (respData && respData.job_id && isImageFilename(respData.filename || filename)) {
            sendImageToFlow(respData.job_id, respData.filename || filename);
          }
          return;
        } else {
          console.warn(`[FlowStudio] Fetch-and-clean returned HTTP ${resp.status}, leaving in trackedDownloadIds for Path B fallback.`);
        }
      } catch (err) {
        console.warn("[FlowStudio] Fetch-and-clean network error, leaving in trackedDownloadIds for Path B fallback:", err);
      }
    }
  } catch (err) {
    console.warn('[FlowStudio] onCreated error:', err);
  }
});

// STEP 4: Path B — Guaranteed Fallback & Flow Project ZIP Interception on state === "complete"
chrome.downloads.onChanged.addListener(async (delta) => {
  if (!delta.state || delta.state.current !== 'complete') return;

  try {
    const settings = await getSettings();
    if (!settings.enabled) return;

    const [dl] = await chrome.downloads.search({ id: delta.id });
    if (dl && dl.filename && dl.filename.toLowerCase().endsWith('.zip')) {
      await handleCompletedZipDownload(dl, settings);
      return;
    }

    const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    if (!trackedDownloadIds.includes(delta.id)) return;

    // Ensure server is online
    const bootRes = await ensureServerOnline(22000);
    if (!bootRes.online) {
      console.error("[FlowStudio] Path B failed: server did not come online within timeout.");
      return;
    }

    if (!dl || !dl.filename) {
      const updated = trackedDownloadIds.filter(x => x !== delta.id);
      await chrome.storage.local.set({ trackedDownloadIds: updated });
      return;
    }

    const filename = dl.filename;
    if (/_clean(\s*\(\d+\))?\.[a-z0-9]+$/i.test(filename) || filename.toLowerCase().includes('.flowtmp_')) {
      const updated = trackedDownloadIds.filter(x => x !== delta.id);
      await chrome.storage.local.set({ trackedDownloadIds: updated });
      return;
    }

    console.log(`[FlowStudio] PATH B: Ingesting completed downloaded file: ${filename}`);
    chrome.action.setBadgeText({ text: "..." });
    chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });

    const ingestPayload = {
      file_path: filename,
      upscale_mode: settings.upscaleMode || "off",
      add_clean_suffix: !!settings.addCleanSuffix,
      copy_image_to_clipboard: true
    };

    const res = await fetch(`${API_BASE}/api/extension/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ingestPayload)
    });

    const { trackedDownloadIds: curTracked = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    await chrome.storage.local.set({ trackedDownloadIds: curTracked.filter(x => x !== delta.id) });
    chrome.downloads.erase({ id: delta.id }, () => {});

    if (res.ok) {
      const ingestData = await res.json().catch(() => ({}));
      chrome.action.setBadgeText({ text: "✓" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);

      // If image and autoFlowMode is active, monitor job until complete then send to Flow
      if (ingestData && ingestData.job_id && isImageFilename(filename)) {
        (async () => {
          const jobId = ingestData.job_id;
          for (let i = 0; i < 60; i++) {
            await new Promise(r => setTimeout(r, 500));
            try {
              const jResp = await fetch(`${API_BASE}/api/jobs/${jobId}`);
              if (jResp.ok) {
                const jData = await jResp.json();
                if (jData.status === "completed") {
                  sendImageToFlow(jobId, filename);
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
      chrome.action.setBadgeText({ text: "!" });
      chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
    }
  } catch (err) {
    console.error('[FlowStudio] Path B failed:', err);
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
  }
});

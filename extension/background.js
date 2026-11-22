// FlowStudio Pro - Background Service Worker (Manifest V3, v3.3.0)
const API_BASE = "http://127.0.0.1:8765";
const CLOUDFLARE_VERSION_URL = "https://flowstudio-api.flowstudio-app.workers.dev/api/version";
const GITHUB_VERSION_URL = "https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json";
const CURRENT_VERSION = "3.3.0";

const DEFAULT_SETTINGS = {
  enabled: false,
  autoWake: true,
  addCleanSuffix: false,
  upscaleMode: "off",
  lastActiveTime: Date.now()
};

const MEDIA_EXTS = ['.mp4', '.mov', '.mkv', '.webm', '.jpg', '.jpeg', '.png', '.webp'];

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

    if (data && data.version && data.version !== CURRENT_VERSION) {
      await chrome.storage.local.set({
        updateAvailable: true,
        remoteVersion: data.version,
        releaseUrl: data.releases_url || data.repo_url || "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover"
      });
      console.log(`[FlowStudio] Update available: v${data.version}`);
    }
  } catch (e) {
    // Offline or network error - ignore silently
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get(null);
  const toSet = { ...DEFAULT_SETTINGS, ...existing, trackedDownloadIds: [] };
  await chrome.storage.local.set(toSet);
  console.log('[FlowStudio] Background Service Worker Initialized (Native Messaging Bridge v3.3.0).');

  // Alarms: 1-min idle check, 60-min self-heal, 24-hr update check
  chrome.alarms.create("checkIdle", { periodInMinutes: 1 });
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

// Message Listener from Popup or Tabs
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const cmd = request.cmd || request.action;
  if (request.type === "TRIGGER_UPDATE" || cmd === "update") {
    sendNative({ cmd: "update" }).then((res) => {
      sendResponse(res);
    });
    return true; // asynchronous response
  }
  if (cmd === "start" || cmd === "stop" || cmd === "status" || cmd === "ping") {
    sendNative({ cmd }).then((res) => {
      sendResponse(res);
    });
    return true; // asynchronous response
  }
});

// 1. Tab Monitoring for Auto-Wake & Activity Tracking
async function checkTabForAutoWake(tab) {
  if (!tab || !tab.url) return;
  const urlLower = tab.url.toLowerCase();
  const isFlow = urlLower.includes("flow.google.com") || urlLower.includes("labs.google");
  const isStudio = urlLower.includes("127.0.0.1:8765") || urlLower.includes("localhost:8765");

  if (isFlow || isStudio) {
    await chrome.storage.local.set({ lastActiveTime: Date.now() });
    const settings = await getSettings();
    if (settings.autoWake && !settings.enabled) {
      console.log("[FlowStudio] Flow tab detected. Auto-waking server bridge via native host...");
      await chrome.storage.local.set({ enabled: true });
      await sendNative({ cmd: "start" });
    }
  }
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.status === "complete") {
    checkTabForAutoWake(tab);
  }
});

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    checkTabForAutoWake(tab);
  } catch (_) {}
});

// Helper to probe server health
async function isServerOnline(timeoutMs = 1200) {
  try {
    const resp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(timeoutMs) });
    return resp.ok;
  } catch (_) {
    return false;
  }
}

// Wait for server online with polling
async function waitForServerOnline(maxWaitMs = 25000, pollIntervalMs = 600) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    if (await isServerOnline(800)) return true;
    await new Promise(r => setTimeout(r, pollIntervalMs));
  }
  return false;
}

// 2. Alarms: Idle Auto-Shutdown & 60-Minute Self-Heal
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "checkIdle") {
    try {
      // Check if any Flow or Studio tabs exist
      const tabs = await chrome.tabs.query({});
      const hasFlowOrStudio = tabs.some(t => {
        const u = (t.url || "").toLowerCase();
        return u.includes("flow.google.com") || u.includes("labs.google") || u.includes("127.0.0.1:8765") || u.includes("localhost:8765");
      });

      if (hasFlowOrStudio) {
        await chrome.storage.local.set({ lastActiveTime: Date.now() });
        return;
      }

      // Check if any server jobs are running
      try {
        const healthResp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(1000) });
        if (healthResp.ok) {
          const hData = await healthResp.json();
          const pools = hData.pools || {};
          const activeJobs = (pools.fast_active || 0) + (pools.fast_queued || 0) + (pools.upscale_active || 0) + (pools.upscale_queued || 0);
          if (activeJobs > 0) {
            await chrome.storage.local.set({ lastActiveTime: Date.now() });
            return;
          }
        }
      } catch (_) {
        // If server is not responding, no jobs running
      }

      const settings = await getSettings();
      const idleMs = Date.now() - (settings.lastActiveTime || Date.now());
      const tenMinutes = 10 * 60 * 1000;

      if (idleMs > tenMinutes) {
        console.log("[FlowStudio] No Flow/Studio tabs and no active jobs for 10 minutes. Idle auto-shutdown...");
        await sendNative({ cmd: "stop" });
        chrome.action.setBadgeText({ text: "" });
      }
    } catch (err) {
      console.warn("[FlowStudio] checkIdle alarm error:", err);
    }
  } else if (alarm.name === "flowstudio_self_heal") {
    try {
      console.log("[FlowStudio] 60-Minute self-heal check running...");
      const tabs = await chrome.tabs.query({});
      const hasFlow = tabs.some(t => {
        const u = (t.url || "").toLowerCase();
        return u.includes("flow.google.com") || u.includes("labs.google");
      });

      if (hasFlow) {
        const online = await isServerOnline(1500);
        const settings = await getSettings();
        if (!online && settings.enabled && settings.autoWake) {
          console.log("[FlowStudio Self-Heal] Flow tab open and server offline; auto-waking bridge...");
          await sendNative({ cmd: "start" });
        }
        // Clean stale tracked download IDs
        const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
        if (trackedDownloadIds.length > 0) {
          const validIds = [];
          for (const id of trackedDownloadIds) {
            try {
              const [d] = await chrome.downloads.search({ id });
              if (d && d.state === 'in_progress') validIds.push(id);
            } catch (_) {}
          }
          await chrome.storage.local.set({ trackedDownloadIds: validIds });
        }
        checkForUpdates();
      }
    } catch (err) {
      console.warn("[FlowStudio] self-heal error:", err);
    }
  } else if (alarm.name === "checkUpdate") {
    checkForUpdates();
  }
});

// 3. Bulletproof Zero-Bypass Download Interception: Path A (Direct URL) & Path B (Fallback / Ingestion)
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

    // Track activity timestamp
    await chrome.storage.local.set({ lastActiveTime: Date.now() });

    // STEP 1: Immediately persist item.id in trackedDownloadIds BEFORE any async network call
    const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    if (!trackedDownloadIds.includes(item.id)) {
      trackedDownloadIds.push(item.id);
      await chrome.storage.local.set({ trackedDownloadIds });
    }

    // STEP 2: Check server health, wake server via native host if offline
    const online = await isServerOnline(1200);
    if (!online && settings.enabled) {
      console.log("[FlowStudio] Server offline during download, firing native host start...");
      sendNative({ cmd: "start" });
    }

    // STEP 3 (PATH A — Direct Clean Fetch):
    // ONLY if server is already ONLINE AND url is HTTPS direct AND NOT blob:
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
          // Success: untrack, cancel and erase chrome download
          const { trackedDownloadIds: cur = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
          await chrome.storage.local.set({ trackedDownloadIds: cur.filter(x => x !== item.id) });
          chrome.downloads.cancel(item.id, () => {
            chrome.downloads.erase({ id: item.id }, () => {});
          });
          chrome.action.setBadgeText({ text: "✓" });
          chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
          setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
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

// STEP 4: Path B — Guaranteed Fallback on onChanged state === "complete"
chrome.downloads.onChanged.addListener(async (delta) => {
  if (!delta.state || delta.state.current !== 'complete') return;

  try {
    const settings = await getSettings();
    if (!settings.enabled) return;

    const { trackedDownloadIds = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    if (!trackedDownloadIds.includes(delta.id)) return;

    // Ensure server is online (wait up to 25s polling)
    const isOnline = await waitForServerOnline(25000);
    if (!isOnline) {
      console.error("[FlowStudio] Path B failed: server did not come online within 25s.");
      return;
    }

    const [dl] = await chrome.downloads.search({ id: delta.id });
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

    // Untrack and erase from Chrome download history
    const { trackedDownloadIds: curTracked = [] } = await chrome.storage.local.get({ trackedDownloadIds: [] });
    await chrome.storage.local.set({ trackedDownloadIds: curTracked.filter(x => x !== delta.id) });
    chrome.downloads.erase({ id: delta.id }, () => {});

    if (res.ok) {
      chrome.action.setBadgeText({ text: "✓" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
      setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
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

// FlowStudio Pro - Invisible Flow.Google.Com Media Content Script (v4.0.0)
// Injects ZERO DOM overlays. Handles Project Drop and Chat Paste cleanly.
(function () {
  'use strict';

  function base64ToDataTransfer(base64, mimeType, filename) {
    const binaryStr = atob(base64);
    const len = binaryStr.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }
    const safeName = filename || "flowstudio_clean.png";
    const safeMime = mimeType || "image/png";
    const file = new File([bytes], safeName, { type: safeMime });
    const dt = new DataTransfer();
    dt.items.add(file);
    return dt;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function createDragEvent(type, clientX, clientY, dt) {
    const evt = new DragEvent(type, {
      bubbles: true,
      cancelable: true,
      composed: true,
      clientX,
      clientY,
      dataTransfer: dt
    });
    try {
      if (!evt.dataTransfer) {
        Object.defineProperty(evt, 'dataTransfer', { value: dt });
      }
    } catch (_) {}
    return evt;
  }

  function findMountedDropOverlay(dropX, dropY, maxLeftBoundary) {
    const matches = [];
    const candidates = document.querySelectorAll(
      '[data-dropzone], [role="region"], [role="dialog"], [role="main"], main, section, div'
    );
    for (const el of candidates) {
      const rect = el.getBoundingClientRect();
      if (rect.width < 100 || rect.height < 100 || rect.left >= maxLeftBoundary) {
        continue;
      }
      if (rect.right <= 0 || rect.bottom <= 0) {
        continue;
      }
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.pointerEvents === 'none') {
        continue;
      }

      const hasDropAttr = el.hasAttribute('data-dropzone');
      const aria = (el.getAttribute('aria-label') || '').toLowerCase();
      const text = (el.innerText || el.textContent || '').toLowerCase();
      const hasDropPhrase =
        text.includes('drop media') ||
        text.includes('drop files') ||
        aria.includes('drop media') ||
        aria.includes('drop files');
      const hasUploadWord = text.includes('upload') || aria.includes('upload');

      if (!hasDropAttr && !hasDropPhrase && !hasUploadWord) {
        continue;
      }

      const coversDropPoint =
        rect.left <= dropX &&
        dropX <= rect.right &&
        rect.top <= dropY &&
        dropY <= rect.bottom;

      matches.push({
        el,
        hasDropAttr,
        hasDropPhrase,
        coversDropPoint,
        area: rect.width * rect.height
      });
    }

    if (matches.length === 0) return null;

    matches.sort((a, b) => {
      if (a.hasDropAttr !== b.hasDropAttr) return a.hasDropAttr ? -1 : 1;
      if (a.coversDropPoint !== b.coversDropPoint) return a.coversDropPoint ? -1 : 1;
      if (a.hasDropPhrase !== b.hasDropPhrase) return a.hasDropPhrase ? -1 : 1;
      return a.area - b.area;
    });
    return matches[0].el;
  }

  function isProjectFileInput(inp, maxLeftBoundary) {
    const r = inp.getBoundingClientRect();
    if (r.width > 0 || r.height > 0) {
      return r.left < maxLeftBoundary;
    }
    let parent = inp.parentElement;
    while (parent && parent !== document.body && parent !== document.documentElement) {
      const pr = parent.getBoundingClientRect();
      if (pr.width > 0 && pr.height > 0) {
        if (pr.left >= maxLeftBoundary) return false;
        break;
      }
      parent = parent.parentElement;
    }
    return !inp.accept || /image|\*/i.test(inp.accept);
  }

  // -------------------------------------------------------------
  // Mode 1: Project Drop (Sustained Drag & Hold - Outside Right Chat)
  // -------------------------------------------------------------
  async function handleProjectDrop(dt) {
    const winWidth = window.innerWidth || 1920;
    const winHeight = window.innerHeight || 1080;
    const maxLeftBoundary = winWidth * 0.65; // strictly outside right-side chat
    const dropX = Math.round(winWidth * 0.36);
    const dropY = Math.round(winHeight * 0.50);

    try {
      dt.effectAllowed = 'all';
      dt.dropEffect = 'copy';
    } catch (_) {}

    const baseTarget = document.elementFromPoint(dropX, dropY) || document.body || document.documentElement;

    // Step 3: Initial dragenter cascade so Flow mounts its project drop overlay
    const enterTargets = Array.from(
      new Set([window, document.documentElement, document.body, baseTarget].filter(Boolean))
    );
    for (const target of enterTargets) {
      target.dispatchEvent(createDragEvent('dragenter', dropX, dropY, dt));
    }

    // Step 4: Sustained Drag & Hold (420ms total - 4 dragover pulses spaced 105ms apart)
    for (let i = 0; i < 4; i++) {
      await sleep(105);
      const mountedOverlay = findMountedDropOverlay(dropX, dropY, maxLeftBoundary);
      const activeTarget = mountedOverlay || document.elementFromPoint(dropX, dropY) || baseTarget;
      if (activeTarget && activeTarget !== window) {
        activeTarget.dispatchEvent(createDragEvent('dragover', dropX, dropY, dt));
      }
      window.dispatchEvent(createDragEvent('dragover', dropX, dropY, dt));
    }

    // Step 5: Settle 80ms, resolve mounted target, dispatch drop, then dragleave 60ms later
    await sleep(80);
    const finalTarget =
      findMountedDropOverlay(dropX, dropY, maxLeftBoundary) ||
      document.elementFromPoint(dropX, dropY) ||
      baseTarget;

    let dropPrevented = false;
    if (finalTarget) {
      const dropEvt = createDragEvent('drop', dropX, dropY, dt);
      finalTarget.dispatchEvent(dropEvt);
      dropPrevented = dropEvt.defaultPrevented;
    }

    if (!dropPrevented) {
      if (document.body && finalTarget !== document.body) {
        const bodyDropEvt = createDragEvent('drop', dropX, dropY, dt);
        document.body.dispatchEvent(bodyDropEvt);
        dropPrevented = dropPrevented || bodyDropEvt.defaultPrevented;
      }
      if (!dropPrevented && finalTarget !== window) {
        const winDropEvt = createDragEvent('drop', dropX, dropY, dt);
        window.dispatchEvent(winDropEvt);
        dropPrevented = dropPrevented || winDropEvt.defaultPrevented;
      }
    }

    await sleep(60);
    if (finalTarget && finalTarget !== window) {
      finalTarget.dispatchEvent(createDragEvent('dragleave', dropX, dropY, dt));
    }
    window.dispatchEvent(createDragEvent('dragleave', dropX, dropY, dt));

    // Step 6: Non-Chat <input type="file"> fallback if drop was NOT defaultPrevented
    let fileInputUsed = false;
    if (!dropPrevented) {
      const fileInputs = document.querySelectorAll('input[type="file"]');
      for (const inp of fileInputs) {
        if (isProjectFileInput(inp, maxLeftBoundary)) {
          try {
            inp.files = dt.files;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            fileInputUsed = true;
            break;
          } catch (_) {}
        }
      }
    }

    return {
      ok: true,
      method: "project_drop",
      targetFound: !!finalTarget,
      dropPrevented,
      fileInputUsed
    };
  }

  // -------------------------------------------------------------
  // Mode 2: Chat Paste (Right-side prompt box - Prompt-Safe)
  // -------------------------------------------------------------
  async function handleChatPaste(dt) {
    const winWidth = window.innerWidth || 1920;
    const minLeftBoundary = winWidth * 0.40; // right-side panel

    // Select candidate input boxes
    const candidates = [
      'textarea[placeholder*="create" i]',
      'textarea[placeholder*="prompt" i]',
      'textarea[placeholder*="describe" i]',
      '[contenteditable="true"][aria-label*="create" i]',
      '[contenteditable="true"][aria-label*="prompt" i]',
      'div[contenteditable="true"][role="textbox"]',
      'textarea',
      '[contenteditable="true"]'
    ];

    let chatInput = null;
    for (const selector of candidates) {
      const elements = document.querySelectorAll(selector);
      for (const el of elements) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 20 && rect.left >= minLeftBoundary) {
          chatInput = el;
          break;
        }
      }
      if (chatInput) break;
    }

    // Fallback: any visible chat input
    if (!chatInput) {
      for (const selector of candidates) {
        const el = document.querySelector(selector);
        if (el) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) {
            chatInput = el;
            break;
          }
        }
      }
    }

    if (!chatInput) {
      return { ok: false, error: "Flow chat input box not found" };
    }

    // Focus without erasing existing prompt text
    chatInput.scrollIntoView({ block: "nearest" });
    chatInput.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    chatInput.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
    chatInput.click();
    chatInput.focus();

    if (chatInput.setSelectionRange && typeof chatInput.value === 'string') {
      const len = chatInput.value.length;
      chatInput.setSelectionRange(len, len);
    }

    // Micro-delay 220ms so framework UI registers cursor focus
    await sleep(220);

    // Dispatch realistic paste event with ClipboardEvent and clipboardData
    let pasteDispatched = false;
    try {
      const pasteEvt = new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: dt
      });
      pasteDispatched = chatInput.dispatchEvent(pasteEvt);
    } catch (_) {
      // Fallback paste event creation
      try {
        const evt = document.createEvent("CustomEvent");
        evt.initCustomEvent("paste", true, true, null);
        evt.clipboardData = dt;
        pasteDispatched = chatInput.dispatchEvent(evt);
      } catch (_) {}
    }

    return { ok: true, method: "chat_paste", pasted: pasteDispatched };
  }

  // -------------------------------------------------------------
  // Message Listener
  // -------------------------------------------------------------
  if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.onMessage && typeof chrome.runtime.onMessage.addListener === "function") {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      try {
        if (message && message.type === "FLOW_ATTACH_IMAGE") {
          const { mode, base64, mimeType, filename } = message;
          if (!base64) {
            sendResponse({ ok: false, error: "No image base64 provided" });
            return true;
          }

          const dt = base64ToDataTransfer(base64, mimeType, filename);
          const work = (mode === "chat_paste") ? handleChatPaste(dt) : handleProjectDrop(dt);
          work
            .then((res) => {
              try { sendResponse(res); } catch (_) {}
            })
            .catch((err) => {
              try { sendResponse({ ok: false, error: err ? err.message : "Flow attach failed" }); } catch (_) {}
            });
          return true; // async sendResponse
        }
      } catch (_) {}
    });
  }

  console.log("[FlowStudio] Flow content script active.");
})();

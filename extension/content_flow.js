// FlowStudio Pro - Invisible Flow.Google.Com Media Content Script (v3.6.0)
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

  // -------------------------------------------------------------
  // Mode 1: Project Drop (Canvas / Dropzone - Outside Right Chat)
  // -------------------------------------------------------------
  async function handleProjectDrop(dt) {
    const winWidth = window.innerWidth || 1920;
    const maxLeftBoundary = winWidth * 0.68; // strictly outside right-side chat

    // Priority A: Search for drop targets or canvas elements
    let dropTarget = null;

    // Search for element with data-dropzone or drop media text
    const allDivs = document.querySelectorAll('[data-dropzone], [role="region"], [role="main"], main, .media-canvas, .dropzone, div');
    for (const el of allDivs) {
      const rect = el.getBoundingClientRect();
      if (rect.width > 200 && rect.height > 200 && rect.left < maxLeftBoundary) {
        const text = (el.innerText || el.textContent || '').toLowerCase();
        if (text.includes("drop media") || text.includes("start creating") || el.hasAttribute("data-dropzone")) {
          dropTarget = el;
          break;
        }
      }
    }

    // Priority B: Center media grid or main canvas container
    if (!dropTarget) {
      const main = document.querySelector('main') || document.querySelector('[role="main"]');
      if (main) {
        const rect = main.getBoundingClientRect();
        if (rect.left < maxLeftBoundary) {
          dropTarget = main;
        }
      }
    }

    // Fallback: document.body
    if (!dropTarget) {
      dropTarget = document.body;
    }

    // HTML5 realistic Drag and Drop Sequence with 80ms spacing
    const enterEvt = new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt });
    dropTarget.dispatchEvent(enterEvt);
    await sleep(80);

    const overEvt = new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt });
    dropTarget.dispatchEvent(overEvt);
    await sleep(80);

    const dropEvt = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt });
    const dropped = dropTarget.dispatchEvent(dropEvt);

    // Also look for project-level input[type="file"] outside chat panel
    const fileInputs = document.querySelectorAll('input[type="file"]');
    for (const inp of fileInputs) {
      const r = inp.getBoundingClientRect();
      if (r.left < maxLeftBoundary || (inp.accept && inp.accept.includes("image"))) {
        try {
          inp.files = dt.files;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          inp.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        } catch (_) {}
      }
    }

    return { ok: true, method: "project_drop", targetFound: !!dropTarget };
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
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message && message.type === "FLOW_ATTACH_IMAGE") {
      const { mode, base64, mimeType, filename } = message;
      if (!base64) {
        sendResponse({ ok: false, error: "No image base64 provided" });
        return true;
      }

      const dt = base64ToDataTransfer(base64, mimeType, filename);
      if (mode === "chat_paste") {
        handleChatPaste(dt).then(res => sendResponse(res));
      } else {
        handleProjectDrop(dt).then(res => sendResponse(res));
      }
      return true; // async sendResponse
    }
  });

  console.log("[FlowStudio] Flow content script active.");
})();

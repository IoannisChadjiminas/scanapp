import { createWorker } from "./lib/worker.js";
import { IDLE_ALARM } from "./lib/constants.js";

const worker = createWorker({
  local: chrome.storage.local,
  session: chrome.storage.session,
  fetchImpl: fetch.bind(globalThis),
  tabs: chrome.tabs,
  scripting: chrome.scripting,
  alarms: chrome.alarms,
  now: () => Date.now(),
  randomId: () => crypto.randomUUID(),
});

function wake(reason) {
  void worker.wake(reason);
}

async function ensureOffscreen() {
  if (!chrome.offscreen?.createDocument || !chrome.runtime.getContexts) {
    return;
  }
  const existing = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
  });
  if (existing.length) {
    return;
  }
  try {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["WORKERS"],
      justification:
        "Poll Scanapp for new Cardmarket jobs without waiting for Chrome's 30-second alarm limit.",
    });
  } catch {
    // Already open, or this Chrome build rejected the offscreen document.
  }
}

chrome.runtime.onInstalled.addListener(() => {
  void ensureOffscreen();
  wake("installed");
});
chrome.runtime.onStartup.addListener(() => {
  void ensureOffscreen();
  wake("startup");
});
chrome.alarms.onAlarm.addListener((alarm) => {
  wake(alarm?.name || IDLE_ALARM);
});
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "keepalive") {
    wake("poll");
  }
});
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  worker.handleMessage(message, sender).then(sendResponse, (error) => {
    sendResponse({ ok: false, error: String(error?.message || error) });
  });
  return true;
});
chrome.tabs.onRemoved.addListener((tabId) => {
  void worker.tabRemoved(tabId);
});
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  void worker.tabUpdated(tabId, info, tab);
});

void worker.installAlarms();
void ensureOffscreen();
wake("init");

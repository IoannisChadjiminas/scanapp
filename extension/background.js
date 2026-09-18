import { createWorker } from "./lib/worker.js";
import { IDLE_ALARM } from "./lib/constants.js";

const worker = createWorker({
  local: chrome.storage.local,
  session: chrome.storage.session,
  fetchImpl: fetch.bind(globalThis),
  tabs: chrome.tabs,
  alarms: chrome.alarms,
  now: () => Date.now(),
  randomId: () => crypto.randomUUID(),
});

function wake(reason) {
  void worker.wake(reason);
}

chrome.runtime.onInstalled.addListener(() => wake("installed"));
chrome.runtime.onStartup.addListener(() => wake("startup"));
chrome.alarms.onAlarm.addListener((alarm) => {
  wake(alarm?.name || IDLE_ALARM);
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
wake("init");

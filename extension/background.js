const DEFAULT_API = "http://127.0.0.1:8000";

async function apiBase() {
  const stored = await chrome.storage.local.get("apiBase");
  return String(stored.apiBase || DEFAULT_API).replace(/\/$/, "");
}

function normalizeUrl(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    parsed.search = "";
    parsed.pathname = parsed.pathname.replace(/\/$/, "");
    return parsed.toString();
  } catch {
    return url;
  }
}

async function nextJob() {
  const base = await apiBase();
  const response = await fetch(`${base}/api/v1/cardmarket/jobs/next`);
  if (response.status === 204) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`jobs ${response.status}`);
  }
  return response.json();
}

async function failJob(jobId) {
  if (!jobId) {
    return;
  }
  const base = await apiBase();
  await fetch(`${base}/api/v1/cardmarket/jobs/${jobId}/fail`, { method: "POST" });
}

async function saveOffers(url, prices, jobId) {
  const base = await apiBase();
  const response = await fetch(`${base}/api/v1/cardmarket/offers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, prices, job_id: jobId || null }),
  });
  if (!response.ok) {
    throw new Error(`offers ${response.status}`);
  }
}

async function ensureTab(url) {
  const wanted = normalizeUrl(url);
  const tabs = await chrome.tabs.query({});
  const existing = tabs.find((tab) => tab.url && normalizeUrl(tab.url) === wanted);
  if (existing?.id) {
    await chrome.tabs.reload(existing.id);
    await chrome.tabs.update(existing.id, { active: true });
    return;
  }
  await chrome.tabs.create({ url: wanted, active: true });
}

const pendingJobs = new Map();

let activeJobId = null;

async function poll() {
  try {
    const job = await nextJob();
    if (!job?.url) {
      return;
    }
    activeJobId = job.id;
    pendingJobs.set(normalizeUrl(job.url), job.id);
    await ensureTab(job.url);
  } catch (error) {
    console.warn("scanapp cardmarket helper", error);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "cardmarket-offers" || !message.url) {
    return undefined;
  }
  const url = normalizeUrl(message.url);
  const jobId = pendingJobs.get(url) || activeJobId;
  const prices = Array.isArray(message.prices) ? message.prices : [];
  if (!prices.length) {
    failJob(jobId)
      .then(() => {
        pendingJobs.delete(url);
        if (jobId && activeJobId === jobId) {
          activeJobId = null;
        }
        sendResponse({ ok: false });
      })
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  saveOffers(url, prices, jobId)
    .then(() => {
      pendingJobs.delete(url);
      if (jobId && activeJobId === jobId) {
        activeJobId = null;
      }
      sendResponse({ ok: true });
    })
    .catch((error) => {
      console.warn("scanapp cardmarket helper", error);
      failJob(jobId)
        .catch(() => undefined)
        .finally(() => sendResponse({ ok: false }));
    });
  return true;
});

function startPolling() {
  chrome.alarms.create("scanapp-cardmarket", { periodInMinutes: 0.5 });
  poll();
}

chrome.runtime.onInstalled.addListener(startPolling);
chrome.runtime.onStartup.addListener(startPolling);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "scanapp-cardmarket") {
    poll();
  }
});
chrome.action.onClicked.addListener(() => {
  poll();
});
setInterval(poll, 4000);
poll();

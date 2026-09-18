import { DEFAULT_API, SERVERS } from "./lib/constants.js";

const connectionEl = document.getElementById("connection");
const activityEl = document.getElementById("activity");
const cardEl = document.getElementById("card");
const queuedEl = document.getElementById("queued");
const successEl = document.getElementById("success");
const failuresEl = document.getElementById("failures");
const pauseBtn = document.getElementById("pause");
const importPageBtn = document.getElementById("import-page");
const importSetBtn = document.getElementById("import-set");
const expansionNoteEl = document.getElementById("expansion-note");
const serverEl = document.getElementById("server");
const customWrap = document.getElementById("custom-wrap");
const customUrl = document.getElementById("custom-url");
const tokenEl = document.getElementById("token");

function connectionLabel(value) {
  if (value === "connected") {
    return "Connection: connected";
  }
  if (value === "authentication_required") {
    return "Connection: authentication required";
  }
  return "Connection: disconnected";
}

function activityLabel(value) {
  if (value === "needs_attention") {
    return "needs attention";
  }
  if (value === "waiting_for_tab") {
    return "waiting for Cardmarket tab";
  }
  if (value === "importing-page") {
    return "importing this set page";
  }
  if (value === "crawling-set") {
    return "crawling whole set";
  }
  return value || "idle";
}

function when(stamp) {
  if (!stamp) {
    return "Never";
  }
  const date = new Date(stamp);
  if (Number.isNaN(date.getTime())) {
    return stamp;
  }
  return date.toLocaleString();
}

function render(status) {
  connectionEl.textContent = connectionLabel(status.connection);
  activityEl.textContent = activityLabel(status.activity);
  if (status.attention) {
    activityEl.textContent = `${activityLabel(status.activity)} — ${status.attention}`;
  }
  cardEl.textContent = status.currentCard || "None";
  queuedEl.textContent = String(status.queued ?? 0);
  successEl.textContent = when(status.lastSuccessAt);
  const failures = Array.isArray(status.recentFailures) ? status.recentFailures : [];
  failuresEl.textContent = failures.length
    ? `Recent failures: ${failures.map((item) => item.reason).join(", ")}`
    : "No recent failures";
  pauseBtn.textContent = status.paused ? "Resume" : "Pause";
  expansionNoteEl.textContent = status.expansionNote || "No set import yet";
  importPageBtn.disabled = Boolean(status.expansionBusy);
  importSetBtn.disabled = Boolean(status.expansionBusy);
  const apiBase = String(status.apiBase || DEFAULT_API).replace(/\/$/, "");
  if (apiBase === SERVERS.local || apiBase === SERVERS.staging) {
    serverEl.value = apiBase;
    customWrap.hidden = true;
  } else {
    serverEl.value = "custom";
    customWrap.hidden = false;
    customUrl.value = apiBase;
  }
  if (status.helperToken) {
    tokenEl.placeholder = "Saved for this server";
  } else {
    tokenEl.placeholder = "Paste helper token";
  }
}

async function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function refresh(message) {
  try {
    const status = await send(message);
    if (status?.error && !status.connection) {
      connectionEl.textContent = `Connection: disconnected (${status.error})`;
      if (status.expansionNote) {
        expansionNoteEl.textContent = status.expansionNote;
      }
      return status;
    }
    if (status) {
      render(status);
    }
    return status;
  } catch (error) {
    connectionEl.textContent = `Connection: disconnected (${error instanceof Error ? error.message : error})`;
    return { error: error instanceof Error ? error.message : String(error) };
  }
}

serverEl.addEventListener("change", () => {
  customWrap.hidden = serverEl.value !== "custom";
});

pauseBtn.addEventListener("click", () => {
  void refresh({ type: pauseBtn.textContent === "Resume" ? "resume" : "pause" });
});
document.getElementById("check").addEventListener("click", () => {
  void refresh({ type: "check-connection" });
});
document.getElementById("open-tab").addEventListener("click", () => {
  void refresh({ type: "open-helper-tab" });
});
document.getElementById("import-page").addEventListener("click", () => {
  expansionNoteEl.textContent = "Importing this page…";
  void refresh({ type: "import-expansion-page" });
});
document.getElementById("import-set").addEventListener("click", () => {
  expansionNoteEl.textContent = "Crawling set…";
  void refresh({ type: "import-expansion-set" });
});
document.getElementById("settings").addEventListener("submit", (event) => {
  event.preventDefault();
  const apiBase = serverEl.value === "custom" ? customUrl.value : serverEl.value;
  void refresh({
    type: "set-settings",
    apiBase,
    helperToken: tokenEl.value || undefined,
  }).then(() => {
    tokenEl.value = "";
  });
});

void refresh({ type: "get-status" });

import { waitForPage } from "./lib/extract.js";
import { hasChallenge } from "./lib/parse.js";
import { classifyUrl } from "./lib/url.js";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "extract-product-image") {
    import(chrome.runtime.getURL("lib/extract.js")).then(({ captureProductImage }) => {
      if (hasChallenge(document, window.location.href, document.title)) {
        sendResponse({ challenge: true, dataUrl: "", src: "" });
        return;
      }
      captureProductImage(document).then(sendResponse);
    });
    return true;
  }
  if (message?.type === "extract-expansion") {
    import(chrome.runtime.getURL("lib/expansion.js")).then(({ collectExpansionSnapshot }) => {
      sendResponse(collectExpansionSnapshot(document, window.location.href, document.title));
    });
    return true;
  }
  if (message?.type !== "extract") {
    return undefined;
  }
  waitForPage(document, window.location.href, document.title).then((result) => {
    const payload = {
      type: "extract-result",
      requestId: message.requestId,
      jobId: message.jobId,
      ...result,
      url: window.location.href,
    };
    sendResponse(payload);
  });
  return true;
});

function send(message) {
  return chrome.runtime.sendMessage(message);
}

function notifyIfChallengeCleared() {
  const href = window.location.href;
  const kind = classifyUrl(href);
  if (kind !== "expansion" && kind !== "singles-index" && kind !== "product") {
    return;
  }
  if (hasChallenge(document, href, document.title)) {
    return;
  }
  if (kind === "product" && !document.querySelector("img.is-front, .card-image img")) {
    return;
  }
  void send({ type: "page-cleared" });
}

function mountMapButton() {
  if (classifyUrl(window.location.href) !== "product") {
    return;
  }
  if (document.getElementById("scanapp-map-host")) {
    return;
  }
  const host = document.createElement("div");
  host.id = "scanapp-map-host";
  host.style.position = "fixed";
  host.style.right = "16px";
  host.style.bottom = "16px";
  host.style.zIndex = "2147483646";
  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .card {
        font: 13px/1.4 system-ui, sans-serif;
        background: #111;
        color: #fff;
        border-radius: 10px;
        padding: 10px 12px;
        box-shadow: 0 8px 24px rgba(0,0,0,.35);
        max-width: 260px;
      }
      button {
        margin-top: 8px;
        width: 100%;
        border: 0;
        border-radius: 8px;
        padding: 8px 10px;
        background: #fff;
        color: #111;
        font-weight: 600;
        cursor: pointer;
      }
      button.secondary { background: #333; color: #fff; }
      button[disabled] { opacity: .6; cursor: default; }
      .muted { opacity: .75; font-size: 12px; }
    </style>
    <div class="card">
      <div class="muted" id="label">Scanapp</div>
      <button type="button" id="save">Save this URL</button>
      <button type="button" id="save-image" class="secondary" hidden>Save listing image</button>
    </div>
  `;
  document.documentElement.appendChild(host);
  const label = shadow.getElementById("label");
  const button = shadow.getElementById("save");
  const imageBtn = shadow.getElementById("save-image");

  async function refresh() {
    const status = await send({ type: "map-status" });
    imageBtn.hidden = !status?.saveUnmatchedImage;
    if (status?.cardId) {
      label.textContent = `Link to ${status.cardLabel || status.cardId}`;
      button.disabled = false;
    } else {
      label.textContent = status?.saveUnmatchedImage
        ? "Save listing image URL if this print is not in TCGdex."
        : "Scan a card first, then save this product URL.";
      button.disabled = true;
    }
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    label.textContent = "Saving…";
    const result = await send({ type: "map-url", url: window.location.href });
    if (result?.ok) {
      label.textContent = `Saved ${result.name || result.card_id}`;
      button.textContent = "Saved";
      return;
    }
    label.textContent = result?.error || "Could not save URL";
    button.disabled = false;
  });

  imageBtn.addEventListener("click", async () => {
    imageBtn.disabled = true;
    label.textContent = "Trying listing image…";
    const result = await send({
      type: "save-unmatched-image",
      url: window.location.href,
      name: document.title || "",
    });
    if (result?.ok && result.stored) {
      label.textContent = "Saved listing image URL";
      imageBtn.textContent = "Image URL saved";
      return;
    }
    if (result?.ok && result.reason === "official_match") {
      label.textContent = "Official TCGdex print already matches this URL.";
      imageBtn.disabled = false;
      return;
    }
    label.textContent = result?.error || "Could not save listing image URL";
    imageBtn.disabled = false;
  });

  void refresh();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    notifyIfChallengeCleared();
    mountMapButton();
  }, { once: true });
} else {
  notifyIfChallengeCleared();
  mountMapButton();
}

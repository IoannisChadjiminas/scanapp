import {
  CHALLENGE_WATCH_MS,
  CHALLENGE_WATCH_TICKS,
  DEFAULT_API,
  DEFAULT_PACE,
  FETCH_TIMEOUT_MS,
  IDLE_ALARM,
  IDLE_PERIOD_MINUTES,
  MAX_EXPANSION_PAGES,
  MAX_EXPANSION_PRODUCTS,
  MAX_EXPANSIONS,
  MAX_RECENT_FAILURES,
  UNMATCHED_IMAGE_BATCH,
  NAV_SPACING_MS,
  PACE_PROFILES,
  PAGE_DEADLINE_MS,
  PARSER_VERSION,
  WAIT_ALARM,
  normalizePace,
} from "./constants.js";
import { CHALLENGE_SELECTOR, challengeTitle } from "./parse.js";
import { isCardmarketListingImageUrl } from "./extract.js";
import { classifyUrl, finalUrlAllowed, normalizeUrl, productIdentity } from "./url.js";
import { expansionDrive } from "./expansion-drive.js";

function expansionCrawlSlug(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function targetCrawlKeys(target) {
  const keys = [];
  const push = (value) => {
    const slug = expansionCrawlSlug(value);
    if (slug && !keys.includes(slug)) {
      keys.push(slug);
    }
  };
  push(target?.id);
  push(target?.name);
  try {
    const parsed = new URL(target?.url || "");
    push(parsed.searchParams.get("idExpansion"));
    const last = parsed.pathname.split("/").filter(Boolean).pop();
    if (last && last.toLowerCase() !== "singles") {
      push(last);
    }
  } catch {
    /* ignore */
  }
  return keys;
}

function crawlAlreadyDone(target, crawls) {
  const keys = new Set(targetCrawlKeys(target));
  if (!keys.size) {
    return false;
  }
  return (crawls || []).some((row) => {
    if (!row?.complete) {
      return false;
    }
    return [row.key, row.expansion, row.expansion_id].some((value) => keys.has(expansionCrawlSlug(value)));
  });
}

function firstUnfinishedIndex(targets, crawls) {
  const index = (targets || []).findIndex((target) => !crawlAlreadyDone(target, crawls));
  return index === -1 ? (targets || []).length : index;
}

function expansionPageKey(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    parsed.pathname = parsed.pathname.replace(/\/$/, "");
    return parsed.toString();
  } catch {
    return String(url || "");
  }
}

function tabBlockReason(tab, snap) {
  if (snap?.challenge) {
    return "challenge";
  }
  const kind = classifyUrl(tab?.url || "");
  if (kind === "login" || kind === "challenge") {
    return kind;
  }
  const title = String(tab?.title || "").toLowerCase();
  if (challengeTitle(title)) {
    return "challenge";
  }
  return null;
}

function shouldPauseCrawl(reason) {
  return reason === "challenge" || reason === "login" || reason === "paused";
}

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const error = new Error("timeout");
      error.code = "timeout";
      reject(error);
    }, ms);
    if (typeof timer === "object" && typeof timer.unref === "function") {
      timer.unref();
    }
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export async function extractInPage(requestId, jobId) {
  const { extractJob } = await import(chrome.runtime.getURL("lib/extract.js"));
  return extractJob(requestId, jobId);
}

async function readStore(store, keys) {
  const result = await store.get(keys);
  return result || {};
}

async function writeStore(store, values) {
  await store.set(values);
}

export function createWorker({
  local,
  session,
  fetchImpl,
  tabs,
  alarms,
  scripting,
  now = () => Date.now(),
  random = Math.random,
  randomId = () => `${now()}-${Math.random().toString(16).slice(2)}`,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  let chain = Promise.resolve();

  function enqueue(task) {
    const run = chain.then(task, task);
    chain = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  async function settings() {
    const stored = await readStore(local, [
      "apiBase",
      "helperToken",
      "helperTokens",
      "paused",
      "expansionPace",
      "saveUnmatchedImage",
    ]);
    const apiBase = String(stored.apiBase || DEFAULT_API).replace(/\/$/, "");
    const byServer =
      stored.helperTokens && typeof stored.helperTokens === "object" ? { ...stored.helperTokens } : {};
    if (stored.helperToken && !byServer[apiBase]) {
      byServer[apiBase] = String(stored.helperToken);
      await writeStore(local, { helperTokens: byServer });
    }
    return {
      apiBase,
      helperToken: String(byServer[apiBase] || stored.helperToken || ""),
      paused: Boolean(stored.paused),
      expansionPace: normalizePace(stored.expansionPace),
      saveUnmatchedImage: Boolean(stored.saveUnmatchedImage),
    };
  }

  function paceProfile(name) {
    return PACE_PROFILES[normalizePace(name)] || PACE_PROFILES[DEFAULT_PACE];
  }

  function jitter(min, max) {
    const lo = Math.min(min, max);
    const hi = Math.max(min, max);
    const skewed = 1 - random() * random();
    return Math.round(lo + skewed * (hi - lo));
  }

  async function humanPause(kind) {
    const pace = paceProfile((await settings()).expansionPace);
    const min = Number(pace[`${kind}Min`]) || 0;
    const max = Number(pace[`${kind}Max`]) || 0;
    if (!max) {
      return;
    }
    let left = jitter(min, max);
    if (left >= 3_000 && random() < Number(pace.hesitateChance || 0)) {
      left += jitter(Number(pace.hesitateMin) || 0, Number(pace.hesitateMax) || 0);
    }
    while (left > 0) {
      if ((await settings()).paused) {
        return;
      }
      const slice = Math.min(left, 250);
      await wait(slice);
      left -= slice;
    }
  }

  async function request(path, { method = "GET", body, timeoutMs } = {}) {
    const { apiBase, helperToken } = await settings();
    if (!helperToken) {
      const error = new Error("authentication required");
      error.code = "auth";
      throw error;
    }
    const headers = { Authorization: `Bearer ${helperToken}` };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs || FETCH_TIMEOUT_MS);
    if (typeof timer === "object" && typeof timer.unref === "function") {
      timer.unref();
    }
    let response;
    try {
      response = await fetchImpl(`${apiBase}/api/v1${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (cause) {
      const error = new Error("disconnected");
      error.code = "network";
      error.cause = cause;
      throw error;
    } finally {
      clearTimeout(timer);
    }
    if (response.status === 401) {
      const error = new Error("authentication required");
      error.code = "auth";
      throw error;
    }
    if (response.status === 204) {
      return null;
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      let detail = payload.detail || `http ${response.status}`;
      if (Array.isArray(detail)) {
        detail = detail.map((item) => item?.msg || JSON.stringify(item)).join("; ");
      }
      if (response.status === 404 && String(path).includes("expansion-import")) {
        detail = `This Scanapp server (${apiBase}) does not have set import yet. Switch the helper to Local Docker.`;
      }
      if (response.status === 404 && String(path).includes("unmatched-products")) {
        detail = `This Scanapp server (${apiBase}) does not list unmatched Cardmarket URLs yet. Switch the helper to Local Docker.`;
      }
      const error = new Error(detail);
      error.code = response.status === 409 ? "claim" : "http";
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  async function patchLocal(values) {
    await writeStore(local, values);
  }

  async function rememberFailure(reason) {
    const stored = await readStore(local, ["recentFailures"]);
    const recent = Array.isArray(stored.recentFailures) ? stored.recentFailures : [];
    recent.unshift({ at: new Date(now()).toISOString(), reason: String(reason || "error") });
    await patchLocal({
      lastFailure: recent[0],
      recentFailures: recent.slice(0, MAX_RECENT_FAILURES),
    });
  }

  async function snapshot() {
    const [localState, sessionState] = await Promise.all([
      readStore(local, null),
      readStore(session, ["helperTabId", "helperDocumentId"]),
    ]);
    return { ...localState, ...sessionState };
  }

  async function publish(partial) {
    await patchLocal(partial);
  }

  async function ensureAlarms() {
    if (!alarms?.create) {
      return;
    }
    await alarms.create(IDLE_ALARM, { periodInMinutes: IDLE_PERIOD_MINUTES });
  }

  async function scheduleWait(ms) {
    if (!alarms?.create) {
      return;
    }
    await alarms.create(WAIT_ALARM, { when: now() + Math.max(ms, 1000) });
  }

  async function helperTab() {
    const stored = await readStore(session, ["helperTabId"]);
    const tabId = stored.helperTabId;
    if (!tabId) {
      return null;
    }
    try {
      return await tabs.get(tabId);
    } catch {
      await writeStore(session, { helperTabId: undefined });
      return null;
    }
  }

  async function abandonHelperTab(reason) {
    await writeStore(session, { helperTabId: null, helperDocumentId: null });
    await patchLocal({
      paused: true,
      attention: reason,
      activity: "needs_attention",
      helperTabClosed: true,
    });
  }

  async function createHelperTab(url, { active = false } = {}) {
    const tab = await tabs.create({ url, active });
    await writeStore(session, { helperTabId: tab.id, helperDocumentId: tab.documentId || null });
    return tab;
  }

  async function releaseCurrent(reason) {
    const stored = await readStore(local, ["currentJob"]);
    const job = stored.currentJob;
    if (!job?.id || !job.claimToken) {
      await patchLocal({ currentJob: null });
      return;
    }
    try {
      await request("/cardmarket/helper/release", {
        method: "POST",
        body: { job_id: job.id, claim_token: job.claimToken, reason },
      });
    } catch {
      /* claim may already be gone */
    }
    await patchLocal({ currentJob: null });
  }

  async function failCurrent(reason, terminal = false) {
    const stored = await readStore(local, ["currentJob"]);
    const job = stored.currentJob;
    if (!job?.id || !job.claimToken) {
      await patchLocal({ currentJob: null });
      return;
    }
    try {
      await request("/cardmarket/helper/fail", {
        method: "POST",
        body: {
          job_id: job.id,
          claim_token: job.claimToken,
          reason,
          terminal,
        },
      });
    } catch {
      /* ignore */
    }
    await rememberFailure(reason);
    await patchLocal({ currentJob: null, currentCard: "", activity: "idle" });
  }

  async function uploadPending() {
    const stored = await readStore(local, ["pendingResult"]);
    const pending = stored.pendingResult;
    if (!pending) {
      return false;
    }
    await publish({ activity: "saving" });
    try {
      await request("/cardmarket/helper/complete", {
        method: "POST",
        body: pending,
      });
      await patchLocal({
        pendingResult: null,
        currentJob: null,
        lastSuccessAt: new Date(now()).toISOString(),
        activity: "idle",
        currentCard: "",
      });
      return true;
    } catch (error) {
      if (error.code === "claim") {
        await patchLocal({ pendingResult: null, currentJob: null });
        return false;
      }
      if (error.code === "network") {
        await publish({ connection: "disconnected", activity: "saving" });
        await scheduleWait(NAV_SPACING_MS);
        return true;
      }
      throw error;
    }
  }

  async function bindExtract(message, sender) {
    const stored = await readStore(local, ["currentJob"]);
    const sessionState = await readStore(session, ["helperTabId", "helperDocumentId"]);
    const job = stored.currentJob;
    if (!job || message?.type !== "extract-result") {
      return { ok: false, reason: "no-job" };
    }
    if (message.requestId !== job.requestId || message.jobId !== job.id) {
      return { ok: false, reason: "stale-message" };
    }
    const senderUrl = normalizeUrl(message.url || sender?.tab?.url || "");
    const fromHelper =
      sender?.tab?.id && sessionState.helperTabId && sender.tab.id === sessionState.helperTabId;
    const fromProduct = Boolean(sender?.tab?.id && finalUrlAllowed(job.url, senderUrl));
    if (sender?.tab?.id && sessionState.helperTabId && !fromHelper && !fromProduct) {
      return { ok: false, reason: "wrong-tab" };
    }
    if (
      !fromProduct &&
      sessionState.helperDocumentId &&
      sender?.documentId &&
      sender.documentId !== sessionState.helperDocumentId
    ) {
      return { ok: false, reason: "wrong-document" };
    }
    const finalUrl = senderUrl || normalizeUrl(message.url || "");
    const kind = classifyUrl(finalUrl);
    if (kind === "login" || kind === "challenge" || message.outcome === "challenge") {
      await publish({ activity: "waiting_for_tab", currentCard: job.card_id || job.url });
      await scheduleWait(2000);
      return { ok: false, reason: "challenge" };
    }
    if (message.outcome === "loading" || kind === "pokemontcg") {
      await scheduleWait(1000);
      return { ok: false, reason: "loading" };
    }
    if (message.outcome === "wrong_product" || kind === "search" || !finalUrlAllowed(job.url, finalUrl)) {
      await failCurrent("wrong_product", true);
      return { ok: false, reason: "wrong-product" };
    }
    const empty = message.outcome === "empty";
    const prices = Array.isArray(message.prices) ? message.prices : [];
    if (message.outcome === "unrecognized" || (!empty && !prices.length)) {
      if (now() - (job.loadStartedAt || now()) >= PAGE_DEADLINE_MS) {
        await failCurrent("parser", false);
        return { ok: false, reason: "parser" };
      }
      await scheduleWait(1000);
      return { ok: false, reason: "loading" };
    }
    const pending = {
      job_id: job.id,
      claim_token: job.claimToken,
      submission_id: job.submissionId,
      url: finalUrl,
      prices,
      empty,
      observed_at: message.observedAt,
      parser_version: message.parserVersion || PARSER_VERSION,
      sampled_offer_count: message.sampledOfferCount ?? prices.length,
    };
    await patchLocal({ pendingResult: pending, activity: "saving" });
    await uploadPending();
    return { ok: true };
  }

  async function extractFromTab(tab, job) {
    if (!tab?.id) {
      return null;
    }
    const message = {
      type: "extract",
      requestId: job.requestId,
      jobId: job.id,
      expectedUrl: job.url,
    };
    if (scripting?.executeScript) {
      try {
        const injected = await scripting.executeScript({
          target: { tabId: tab.id },
          files: ["inject-extract.js"],
        });
        const payload = Array.isArray(injected) ? injected[0]?.result : injected?.result;
        if (payload?.outcome) {
          return payload;
        }
      } catch {
        /* fall through */
      }
      try {
        const injected = await scripting.executeScript({
          target: { tabId: tab.id },
          func: extractInPage,
          args: [job.requestId, job.id],
        });
        const payload = Array.isArray(injected) ? injected[0]?.result : injected?.result;
        if (payload?.outcome) {
          return payload;
        }
      } catch {
        /* fall through to the content-script message */
      }
    }
    if (!tabs.sendMessage) {
      return null;
    }
    try {
      return await tabs.sendMessage(
        tab.id,
        message,
        tab.documentId ? { documentId: tab.documentId } : undefined,
      );
    } catch {
      try {
        return await tabs.sendMessage(tab.id, message);
      } catch {
        return null;
      }
    }
  }

  async function findOpenProductTab(target) {
    if (typeof tabs.query !== "function") {
      return null;
    }
    let found = [];
    try {
      found = await tabs.query({
        url: ["https://www.cardmarket.com/*", "https://cardmarket.com/*"],
      });
    } catch {
      return null;
    }
    return (
      found.find((tab) => {
        const href = tab.url || "";
        if (normalizeUrl(href) === normalizeUrl(target)) {
          return true;
        }
        const expected = productIdentity(target);
        const actual = productIdentity(href);
        return Boolean(expected) && expected === actual;
      }) || null
    );
  }

  async function adoptTab(tab) {
    if (!tab?.id) {
      return;
    }
    await writeStore(session, {
      helperTabId: tab.id,
      helperDocumentId: tab.documentId || null,
    });
    await patchLocal({ helperTabClosed: false });
  }

  async function loadJob(job) {
    const target = job.url;
    await publish({ activity: "fetching", currentCard: job.card_id || job.url });
    const expectedIdentity = job.productIdentity || productIdentity(target);
    let tab = null;
    if (!String(expectedIdentity || "").startsWith("pokemontcg:")) {
      tab = await findOpenProductTab(target);
    }
    if (!tab) {
      tab = await helperTab();
    }
    if (!tab) {
      tab = await createHelperTab(target, { active: true });
      await patchLocal({
        lastNavigationAt: now(),
        currentJob: { ...job, phase: "loading", loadStartedAt: now(), navigatedTo: target },
      });
      return;
    }
    await adoptTab(tab);
    const currentUrl = tab.url || "";
    const alreadyThere =
      normalizeUrl(currentUrl) === normalizeUrl(target) ||
      (Boolean(productIdentity(target)) && productIdentity(target) === productIdentity(currentUrl)) ||
      (String(expectedIdentity || "").startsWith("pokemontcg:") &&
        classifyUrl(currentUrl) === "product" &&
        job.navigatedTo === target);
    if (!alreadyThere) {
      await tabs.update(tab.id, { url: target, active: true });
      await patchLocal({
        lastNavigationAt: now(),
        currentJob: { ...job, phase: "loading", loadStartedAt: now(), navigatedTo: target },
      });
      return;
    }
    if (tab.id && tabs.update) {
      await tabs.update(tab.id, { active: true });
    }
    const kind = classifyUrl(currentUrl);
    if (kind === "login" || kind === "challenge") {
      await publish({
        activity: "waiting_for_tab",
        currentCard: job.card_id || job.url,
      });
      await scheduleWait(2000);
      return;
    }
    if (kind !== "product") {
      await scheduleWait(1000);
      return;
    }
    const result = await extractFromTab(tab, job);
    if (result?.outcome) {
      await bindExtract(
        { type: "extract-result", ...result, requestId: job.requestId, jobId: job.id },
        { tab, documentId: tab.documentId },
      );
      return;
    }
    await patchLocal({ currentJob: { ...job, phase: "extracting" } });
    await scheduleWait(1000);
  }

  async function tick() {
    await ensureAlarms();
    const { helperToken, paused, apiBase } = await settings();
    if (paused) {
      const resumed = await maybeResumeFromOpenTabs();
      if (resumed) {
        return;
      }
    }
    if (!helperToken) {
      await publish({ connection: "authentication_required", activity: "idle" });
      return;
    }
    try {
      const status = await request("/cardmarket/helper/status", {
        method: "POST",
        body: {
          ready: !paused,
          paused,
          attention: paused ? (await readStore(local, ["attention"])).attention : null,
          current_job_id: (await readStore(local, ["currentJob"])).currentJob?.id || null,
        },
      });
      await publish({
        connection: "connected",
        queued: status.queued ?? status.pending ?? 0,
        helperReady: status.helper_ready,
      });
    } catch (error) {
      await publish({
        connection: error.code === "auth" ? "authentication_required" : "disconnected",
        activity: paused ? "paused" : "idle",
      });
      return;
    }
    if (await uploadPending()) {
      return;
    }
    if (paused) {
      await publish({ activity: (await readStore(local, ["attention"])).attention ? "needs_attention" : "paused" });
      return;
    }
    if ((await readStore(local, ["expansionBusy"])).expansionBusy) {
      return;
    }
    const stored = await readStore(local, ["currentJob", "lastCardId", "lastCardLabel"]);
    let job = stored.currentJob;
    let claimed;
    try {
      claimed = await request("/cardmarket/helper/claim", { method: "POST", body: {} });
    } catch (error) {
      if (error.code === "claim") {
        await patchLocal({ currentJob: null, pendingResult: null });
        return;
      }
      return;
    }
    if (!claimed?.id || claimed.status === "idle") {
      await patchLocal({ currentJob: null, pendingResult: null });
      await publish({ activity: "idle", currentCard: "", queued: claimed?.queued || 0 });
      return;
    }
    if (!job || job.id !== claimed.id) {
      job = {
        id: claimed.id,
        url: claimed.url,
        card_id: claimed.card_id,
        claimToken: claimed.claim_token,
        claimExpiresAt: claimed.claim_expires_at,
        productIdentity: claimed.product_identity,
        filters: claimed.filters || {},
        requestId: randomId(),
        submissionId: randomId(),
        phase: "claimed",
        loadStartedAt: now(),
      };
    } else {
      await request("/cardmarket/helper/renew", {
        method: "POST",
        body: { job_id: job.id, claim_token: job.claimToken },
      }).catch(() => undefined);
      job = { ...job, ...claimed, claimToken: claimed.claim_token || job.claimToken };
    }
    await patchLocal({
      currentJob: job,
      currentCard: job.card_id || job.url,
      lastCardId: job.card_id || stored.lastCardId,
      lastCardLabel: job.card_id || stored.lastCardLabel,
    });
    await loadJob(job);
  }

  async function mapStatus() {
    const stored = await readStore(local, ["currentJob", "lastCardId", "lastCardLabel"]);
    const job = stored.currentJob;
    const cardId = String(job?.card_id || stored.lastCardId || "");
    const settingsState = await settings();
    return {
      cardId,
      cardLabel: String(job?.card_id || stored.lastCardLabel || cardId),
      saveUnmatchedImage: Boolean(settingsState.saveUnmatchedImage),
    };
  }

  async function mapCurrentUrl(url, cardId) {
    const stored = await mapStatus();
    const targetId = String(cardId || stored.cardId || "");
    if (!targetId) {
      const error = new Error("Scan a card first so the helper knows which print to link");
      error.code = "http";
      throw error;
    }
    return request("/cardmarket/helper/map", {
      method: "POST",
      body: { url, card_id: targetId },
    });
  }

  function inspectProductPage(selector) {
    const title = document.title || "";
    const href = location.href || "";
    const text = String(document.body?.innerText || "").slice(0, 2_000).toLowerCase();
    const cf = Boolean(
      document.querySelector(selector) ||
        title.toLowerCase().includes("just a moment") ||
        title.toLowerCase().includes("einen moment") ||
        title.toLowerCase().includes("attention required") ||
        title.toLowerCase().includes("verify you are human") ||
        title.toLowerCase().includes("checking your browser") ||
        text.includes("just a moment") ||
        text.includes("verify you are human") ||
        text.includes("checking your browser"),
    );
    const nodes = document.querySelectorAll(
      "img.is-front, .card-image img.is-front, #image img.is-front, #image img, .card-image img, img[itemprop='image']",
    );
    let best = null;
    for (const img of nodes) {
      const src = String(img.currentSrc || img.src || "");
      const host = (() => {
        try {
          return new URL(src).hostname.toLowerCase();
        } catch {
          return "";
        }
      })();
      if (
        !host.endsWith("product-images.s3.cardmarket.com") &&
        host !== "product-images.s3.cardmarket.com" &&
        host !== "static.cardmarket.com" &&
        !host.endsWith(".static.cardmarket.com")
      ) {
        continue;
      }
      if (/logo|favicon|icon|placeholder|sprite/i.test(src)) {
        continue;
      }
      const width = Number(img.naturalWidth || img.width || 0);
      const height = Number(img.naturalHeight || img.height || 0);
      const isFront = img.classList?.contains("is-front");
      const inMain = Boolean(img.closest("#image, .card-image, .is-product-image, .image"));
      const score = (inMain ? 1_000_000_000 : 0) + (isFront ? 100_000_000 : 0) + width * height;
      if (!best || score > best.score) {
        best = { src, ready: Boolean(img.complete && width >= 80), score };
      }
    }
    return {
      title,
      url: href,
      cf,
      listingSrc: best?.src || "",
      listingReady: Boolean(best?.ready),
      hasListingImage: Boolean(best?.src),
      ready: Boolean(
        document.querySelector(
          'select[name="idExpansion"], select#idExpansion, table.table, .table-body, img.is-front, #image img',
        ),
      ),
    };
  }

  async function extractProductImageFromTab(tab) {
    if (tab?.id && tabs.sendMessage) {
      try {
        const captured = await withTimeout(
          tabs.sendMessage(tab.id, { type: "extract-product-image" }),
          FETCH_TIMEOUT_MS,
        );
        if (captured?.challenge || captured?.dataUrl || captured?.src) {
          return captured;
        }
      } catch {
        /* content script may not be ready after navigation */
      }
    }
    if (!tab?.id || typeof scripting?.executeScript !== "function") {
      return { challenge: true, src: "", dataUrl: "" };
    }
    try {
      const injected = await withTimeout(
        scripting.executeScript({
          target: { tabId: tab.id },
          args: [CHALLENGE_SELECTOR],
          func: inspectProductPage,
        }),
        FETCH_TIMEOUT_MS,
      );
      const payload = Array.isArray(injected) ? injected[0]?.result : injected?.result;
      if (!payload) {
        return { challenge: true, src: "", dataUrl: "" };
      }
      return {
        challenge: Boolean(payload.cf || payload.challenge),
        src: String(payload.listingSrc || payload.src || ""),
        dataUrl: String(payload.dataUrl || ""),
      };
    } catch {
      return { challenge: true, src: "", dataUrl: "" };
    }
  }

  async function captureListingImage() {
    const tab = await helperTab();
    const live = await liveTabState(tab);
    const blocked = tabBlockReason(
      { ...tab, title: live.title || tab?.title, url: live.url || tab?.url },
      { challenge: live.cf },
    );
    if (shouldPauseCrawl(blocked)) {
      const error = new Error("Cloudflare");
      error.code = "challenge";
      throw error;
    }
    const captured = await extractProductImageFromTab(tab);
    if (!captured || captured.challenge) {
      const error = new Error("Cloudflare");
      error.code = "challenge";
      throw error;
    }
    const src = String(captured.src || "");
    if (!src || !isCardmarketListingImageUrl(src)) {
      const error = new Error("No listing image URL on this Cardmarket page");
      error.code = "http";
      throw error;
    }
    return { src };
  }

  async function saveUnmatchedListingImage(url, name) {
    const captured = await captureListingImage();
    return request("/cardmarket/helper/unmatched-image", {
      method: "POST",
      body: {
        url,
        name: name || "",
        image_url: captured.src,
      },
    });
  }

  async function extractExpansionFromTab(tab) {
    if (!tab?.id) {
      return null;
    }
    const fallbackChallenge = { challenge: true, products: [], expansions: [], nextPage: null };
    if (scripting?.executeScript) {
      try {
        const injected = await withTimeout(
          scripting.executeScript({
            target: { tabId: tab.id },
            files: ["expansion-extract.js"],
          }),
          FETCH_TIMEOUT_MS,
        );
        const payload = Array.isArray(injected) ? injected[0]?.result : injected?.result;
        if (payload?.challenge || (payload && (payload.products || payload.expansions))) {
          return payload;
        }
      } catch {
        /* fall through */
      }
    }
    if (tabs.sendMessage) {
      try {
        const payload = await withTimeout(
          tabs.sendMessage(
            tab.id,
            { type: "extract-expansion" },
            tab.documentId ? { documentId: tab.documentId } : undefined,
          ),
          FETCH_TIMEOUT_MS,
        );
        if (payload) {
          return payload;
        }
      } catch {
        try {
          const payload = await withTimeout(
            tabs.sendMessage(tab.id, { type: "extract-expansion" }),
            FETCH_TIMEOUT_MS,
          );
          if (payload) {
            return payload;
          }
        } catch {
          /* challenge fallback */
        }
      }
    }
    return fallbackChallenge;
  }

  async function activeCardmarketTab(kinds) {
    if (typeof tabs.query !== "function") {
      return null;
    }
    const matches = (tab) => kinds.includes(classifyUrl(tab?.url || ""));
    try {
      const focused = await tabs.query({
        active: true,
        lastFocusedWindow: true,
      });
      const current = focused.find(matches);
      if (current) {
        return current;
      }
    } catch {
      /* some test harnesses ignore query filters */
    }
    try {
      const found = await tabs.query({
        url: ["https://www.cardmarket.com/*", "https://cardmarket.com/*"],
      });
      return found.find(matches) || null;
    } catch {
      return null;
    }
  }

  async function waitForExpansionPage(tabId) {
    const started = now();
    while (now() - started < PAGE_DEADLINE_MS) {
      let tab;
      try {
        tab = await tabs.get(tabId);
      } catch {
        return null;
      }
      if (tabBlockReason(tab) || (await settings()).paused) {
        return tab;
      }
      const kind = classifyUrl(tab.url || "");
      if ((!tab.status || tab.status === "complete") && kind === "expansion") {
        return tab;
      }
      await wait(250);
    }
    try {
      return await tabs.get(tabId);
    } catch {
      return null;
    }
  }

  async function waitForProductPage(tabId, { expectUrl = "", previousSrc = "" } = {}) {
    const started = now();
    const wanted = normalizeUrl(expectUrl);
    const previous = String(previousSrc || "");
    while (now() - started < PAGE_DEADLINE_MS) {
      let tab;
      try {
        tab = await tabs.get(tabId);
      } catch {
        return null;
      }
      const live = await liveTabState(tab);
      const merged = {
        ...tab,
        title: live.title || tab?.title,
        url: live.url || tab?.url,
      };
      if (tabBlockReason(merged, { challenge: live.cf }) || (await settings()).paused) {
        return merged;
      }
      const kind = classifyUrl(merged.url || "");
      if (wanted && normalizeUrl(merged.url || "") !== wanted) {
        await wait(250);
        continue;
      }
      if ((!tab.status || tab.status === "complete") && kind === "product") {
        if (live.cf || live.inspected === false) {
          return merged;
        }
        const src = String(live.listingSrc || "");
        if (src && previous && src === previous) {
          await wait(250);
          continue;
        }
        if (src && (live.listingReady || !previous)) {
          return merged;
        }
        if (!previous && live.hasListingImage) {
          return merged;
        }
      }
      await wait(250);
    }
    try {
      return await tabs.get(tabId);
    } catch {
      return null;
    }
  }

  async function crawlExpansionPages(tab, { crawl, seen, totals }) {
    let current = tab;
    let pages = 0;
    let lastResult = {
      stored: 0,
      linked: 0,
      unmatched: 0,
      products: 0,
      source: crawl ? "crawl" : "page",
    };
    while (pages < MAX_EXPANSION_PAGES && seen.size < MAX_EXPANSION_PRODUCTS) {
      if ((await settings()).paused) {
        lastResult = { ...lastResult, stopped: "paused" };
        break;
      }
      if (crawl) {
        await humanPause("read");
        if ((await settings()).paused) {
          lastResult = { ...lastResult, stopped: "paused" };
          break;
        }
      }
      pages += 1;
      const snap = await extractExpansionFromTab(current);
      const blocked = tabBlockReason(current, snap);
      if (blocked) {
        lastResult = { ...lastResult, stopped: blocked };
        break;
      }
      const products = Array.isArray(snap?.products) ? snap.products : [];
      const pageUrl = snap?.pageUrl || current.url;
      lastResult = await request("/cardmarket/helper/expansion-import", {
        method: "POST",
        body: {
          page_url: pageUrl,
          products,
          source: crawl ? "crawl" : "page",
        },
      });
      totals.stored += Number(lastResult.stored || 0);
      totals.linked += Number(lastResult.linked || 0);
      totals.unmatched += Number(lastResult.unmatched || 0);
      for (const item of products) {
        if (item?.url) {
          seen.add(item.url);
        }
      }
      if (!crawl) {
        return { lastResult, pages, current };
      }
      const next = snap?.nextPage;
      if (!next || expansionPageKey(next) === expansionPageKey(current.url || pageUrl)) {
        break;
      }
      await humanPause("page");
      if ((await settings()).paused) {
        lastResult = { ...lastResult, stopped: "paused" };
        break;
      }
      await tabs.update(current.id, { url: next, active: true });
      current = (await waitForExpansionPage(current.id)) || (await tabs.get(current.id));
      const nextBlock = tabBlockReason(current);
      if (nextBlock) {
        lastResult = { ...lastResult, stopped: nextBlock };
        break;
      }
      if (classifyUrl(current?.url || "") !== "expansion") {
        lastResult = { ...lastResult, stopped: classifyUrl(current?.url || "") || "navigation" };
        break;
      }
      await humanPause("settle");
      current = (await tabs.get(current.id)) || current;
      const settled = tabBlockReason(current);
      if (settled) {
        lastResult = { ...lastResult, stopped: settled };
        break;
      }
    }
    return { lastResult, pages, current };
  }

  async function driveExpansion(tabId, action, payload) {
    if (!tabId || !scripting?.executeScript) {
      return null;
    }
    try {
      const injected = await withTimeout(
        scripting.executeScript({
          target: { tabId },
          world: "MAIN",
          func: expansionDrive,
          args: [action, payload || {}],
        }),
        FETCH_TIMEOUT_MS,
      );
      return Array.isArray(injected) ? injected[0]?.result : injected?.result;
    } catch {
      try {
        const injected = await withTimeout(
          scripting.executeScript({
            target: { tabId },
            func: expansionDrive,
            args: [action, payload || {}],
          }),
          FETCH_TIMEOUT_MS,
        );
        return Array.isArray(injected) ? injected[0]?.result : injected?.result;
      } catch {
        return null;
      }
    }
  }

  async function importExpansion({ crawl = false } = {}) {
    const tab = await activeCardmarketTab(["expansion", "singles-index"]);
    if (!tab?.id) {
      const error = new Error("Open a Cardmarket set list in this window first");
      error.code = "http";
      throw error;
    }
    if (classifyUrl(tab.url || "") === "singles-index") {
      const error = new Error(
        "This is the All Singles page. Pick one expansion in the dropdown, or use Import all expansions.",
      );
      error.code = "http";
      throw error;
    }
    await patchLocal({
      expansionBusy: true,
      activity: crawl ? "crawling-set" : "importing-page",
      expansionNote: crawl ? "Crawling set…" : "Importing this page…",
    });
    const seen = new Set();
    const totals = { stored: 0, linked: 0, unmatched: 0 };
    try {
      const { lastResult, pages } = await crawlExpansionPages(tab, { crawl, seen, totals });
      const stopped = shouldPauseCrawl(lastResult.stopped);
      if (crawl && !stopped && seen.size) {
        const replaced = await request("/cardmarket/helper/expansion-import", {
          method: "POST",
          body: {
            page_url: tab.url || "",
            products: [...seen].map((url) => ({ url })),
            source: "crawl",
            complete: true,
            replace: true,
          },
        });
        Object.assign(lastResult, replaced);
      }
      const note = stopped
        ? `Paused (${lastResult.stopped}). Kept ${totals.stored} stored URLs. Pass Cloudflare, then import this set again.`
        : crawl
          ? `Replaced this set with ${seen.size} URLs · linked ${lastResult.linked ?? totals.linked} · unmatched ${lastResult.unmatched ?? totals.unmatched}`
          : `Stored ${lastResult.stored ?? seen.size} URLs · linked ${lastResult.linked ?? 0} · unmatched ${lastResult.unmatched ?? 0}`;
      await patchLocal({
        lastExpansionImport: { ...lastResult, pages, productsSeen: seen.size },
        expansionNote: note,
        ...(stopped ? { paused: true, activity: "paused" } : {}),
      });
      return lastResult;
    } finally {
      await patchLocal({ expansionBusy: false, activity: "idle" });
    }
  }

  async function notifyPhone(body) {
    const stored = await readStore(local, ["ntfyTopic"]);
    const topic = String(stored.ntfyTopic || "").trim();
    if (!/^[A-Za-z0-9_-]{8,120}$/.test(topic)) {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5_000);
    if (typeof timer === "object" && typeof timer.unref === "function") {
      timer.unref();
    }
    try {
      await fetchImpl(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
        method: "POST",
        headers: {
          Title: "Scanapp Cardmarket",
          Priority: "high",
          Tags: "warning",
        },
        body: String(body || "Cloudflare paused the crawl. Tick the box on the Mac, then Continue."),
        signal: controller.signal,
      });
    } catch {
      /* phone notify is best-effort */
    } finally {
      clearTimeout(timer);
    }
  }

  async function openExpansionInTab(tab, target) {
    const nextUrl = target?.url;
    if (nextUrl) {
      const same = expansionPageKey(tab?.url || "") === expansionPageKey(nextUrl);
      if (same && typeof tabs.reload === "function") {
        await tabs.reload(tab.id);
      } else {
        await tabs.update(tab.id, { url: nextUrl, active: true });
      }
      return;
    }
    await driveExpansion(tab.id, "apply", {
      id: target?.id,
      name: target?.name,
      url: target?.url,
    });
  }

  async function pauseAllExpansions({ reason, index, targets, totals, label, tabId }) {
    const challenge = reason === "challenge" || reason === "login";
    const note =
      `Paused at set ${index + 1}/${targets.length}: ${label}` +
      (challenge ? " (Cloudflare)" : "") +
      `. Kept ${totals.stored} stored URLs. ` +
      (challenge
        ? "The Cardmarket tab is in front — tick the box. The crawl continues once the page loads. Continue still works if it does not."
        : "Press Continue to keep going.");
    if (tabId) {
      try {
        await tabs.update(tabId, { active: true });
      } catch {
        /* tab may already be gone */
      }
    }
    await patchLocal({
      paused: true,
      expansionResume: {
        index,
        targets,
        totals: { stored: totals.stored, linked: totals.linked, unmatched: totals.unmatched },
        reason,
      },
      lastExpansionImport: {
        stopped: reason,
        expansions: targets.length,
        expansionIndex: index + 1,
        stored: totals.stored,
        linked: totals.linked,
        unmatched: totals.unmatched,
      },
      expansionNote: note,
      attention: challenge
        ? "Tick Cloudflare in the Cardmarket tab. The crawl continues after the page loads."
        : "Press Continue",
      activity: "paused",
    });
    if (challenge) {
      await notifyPhone(
        `Cloudflare on ${label}. Tick the box on the Mac. The crawl continues once the page loads.`,
      );
      void watchPausedChallenge(tabId);
    }
  }

  async function loadImportedCrawls() {
    try {
      const payload = await request("/cardmarket/helper/expansion-crawls");
      return Array.isArray(payload?.expansions) ? payload.expansions : [];
    } catch {
      return [];
    }
  }

  async function loadUnmatchedProducts(after) {
    const query = new URLSearchParams();
    if (after) {
      query.set("after", after);
    }
    query.set("limit", String(UNMATCHED_IMAGE_BATCH));
    return request(`/cardmarket/helper/unmatched-products?${query.toString()}`, {
      timeoutMs: 30_000,
    });
  }

  async function pauseUnmatchedImages({ reason, after, totals, label, tabId }) {
    const challenge = reason === "challenge" || reason === "login";
    const note =
      `Paused unmatched listing images at ${label}` +
      (challenge ? " (Cloudflare)" : "") +
      `. Stored ${totals.stored} · skipped ${totals.skipped} · failed ${totals.failed}. ` +
      (challenge
        ? "The Cardmarket tab is in front — tick the box. The crawl continues once the page loads. Continue still works if it does not."
        : "Press Continue to keep going.");
    if (tabId) {
      try {
        await tabs.update(tabId, { active: true });
      } catch {
        /* tab may already be gone */
      }
    }
    await patchLocal({
      paused: true,
      expansionResume: {
        kind: "unmatched-images",
        after,
        totals: {
          stored: totals.stored,
          skipped: totals.skipped,
          failed: totals.failed,
        },
        reason,
      },
      expansionNote: note,
      attention: challenge
        ? "Tick Cloudflare in the Cardmarket tab. The crawl continues after the page loads."
        : "Press Continue",
      activity: "paused",
    });
    if (challenge) {
      await notifyPhone(
        `Cloudflare on unmatched listing ${label}. Tick the box on the Mac. The crawl continues once the page loads.`,
      );
      void watchPausedChallenge(tabId);
    }
  }

  async function bindHelperTab(tab) {
    if (!tab?.id) {
      return tab;
    }
    await writeStore(session, {
      helperTabId: tab.id,
      helperDocumentId: tab.documentId || null,
    });
    return tab;
  }

  async function importUnmatchedImages({ resume: resumeFromCheckpoint = false } = {}) {
    const previous = await readStore(local, ["expansionBusy", "expansionResume"]);
    if (previous.expansionBusy) {
      const error = new Error("A Cardmarket crawl is already running.");
      error.code = "http";
      throw error;
    }
    const saved =
      previous.expansionResume && typeof previous.expansionResume === "object"
        ? previous.expansionResume
        : null;
    if (
      !resumeFromCheckpoint &&
      saved &&
      saved.kind !== "unmatched-images" &&
      (saved.targets?.length || saved.index != null)
    ) {
      const error = new Error(
        "An expansion crawl is paused. Press Continue for that crawl first.",
      );
      error.code = "http";
      throw error;
    }
    const resume = saved?.kind === "unmatched-images" ? saved : null;
    let after = resume?.after || "";
    const totals = {
      stored: Number(resume?.totals?.stored) || 0,
      skipped: Number(resume?.totals?.skipped) || 0,
      failed: Number(resume?.totals?.failed) || 0,
    };
    await patchLocal({
      paused: false,
      expansionBusy: true,
      activity: "crawling-unmatched-images",
      attention: null,
      expansionNote: resume
        ? "Continuing unmatched listing images…"
        : "Loading unmatched Cardmarket URLs…",
    });
    try {
      let current =
        (await helperTab()) ||
        (await activeCardmarketTab(["product", "expansion", "singles-index"]));
      if (current?.id) {
        current = await bindHelperTab(current);
      }
      let halted = false;
      let previousListingSrc = "";
      while (!halted) {
        if ((await settings()).paused) {
          await pauseUnmatchedImages({
            reason: "paused",
            after,
            totals,
            label: after || "start",
            tabId: current?.id,
          });
          halted = true;
          break;
        }
        const batch = await loadUnmatchedProducts(after);
        const products = Array.isArray(batch?.products) ? batch.products : [];
        const remaining = Number(batch?.total) || 0;
        if (!products.length) {
          const examined = String(batch?.examined || "");
          if (batch?.has_more && examined && examined !== after) {
            after = examined;
            continue;
          }
          await patchLocal({
            expansionResume: null,
            expansionNote:
              `Unmatched listing image URLs done. Stored ${totals.stored} · skipped ${totals.skipped} · failed ${totals.failed}` +
              (remaining ? ` · ${remaining} still unmatched.` : "."),
          });
          break;
        }
        if (!current?.id) {
          current = await createHelperTab(products[0].url, { active: true });
        }
        for (const item of products) {
          if ((await settings()).paused) {
            await pauseUnmatchedImages({
              reason: "paused",
              after,
              totals,
              label: item.name || item.url,
              tabId: current.id,
            });
            halted = true;
            break;
          }
          const label = item.name || item.url;
          const visited = totals.stored + totals.skipped + totals.failed + 1;
          await patchLocal({
            activity: "crawling-unmatched-images",
            expansionNote: `Unmatched listing ${visited} · ${remaining} still unmatched: ${label}`,
            expansionResume: {
              kind: "unmatched-images",
              after,
              totals: { stored: totals.stored, skipped: totals.skipped, failed: totals.failed },
              reason: "running",
            },
          });
          await humanPause("think");
          if ((await settings()).paused) {
            await pauseUnmatchedImages({
              reason: "paused",
              after,
              totals,
              label,
              tabId: current.id,
            });
            halted = true;
            break;
          }
          const here = normalizeUrl(current.url || "");
          const target = normalizeUrl(item.url);
          if (here !== target) {
            await tabs.update(current.id, { url: item.url, active: true });
          } else {
            await tabs.update(current.id, { active: true });
          }
          current = (await waitForProductPage(current.id, {
            expectUrl: item.url,
            previousSrc: previousListingSrc,
          })) || (await tabs.get(current.id));
          current = await bindHelperTab(current);
          await humanPause("settle");
          if ((await settings()).paused) {
            await pauseUnmatchedImages({
              reason: "paused",
              after,
              totals,
              label,
              tabId: current.id,
            });
            halted = true;
            break;
          }
          const live = await liveTabState(current);
          const blocked = tabBlockReason(
            { ...current, title: live.title || current?.title, url: live.url || current?.url },
            { challenge: live.cf },
          );
          if (shouldPauseCrawl(blocked)) {
            await pauseUnmatchedImages({
              reason: blocked,
              after,
              totals,
              label,
              tabId: current.id,
            });
            halted = true;
            break;
          }
          if (classifyUrl((live.url || current?.url) || "") !== "product") {
            totals.failed += 1;
            after = item.url;
            continue;
          }
          try {
            const result = await saveUnmatchedListingImage(item.url, item.name || "");
            if (result?.image_url) {
              previousListingSrc = String(result.image_url);
            }
            if (result?.stored) {
              totals.stored += 1;
            } else {
              totals.skipped += 1;
            }
          } catch (error) {
            if (error?.code === "challenge" || error?.code === "login") {
              await pauseUnmatchedImages({
                reason: error.code,
                after,
                totals,
                label,
                tabId: current.id,
              });
              halted = true;
              break;
            }
            totals.failed += 1;
          }
          after = item.url;
          await humanPause("page");
          break;
        }
      }
      return totals;
    } finally {
      await patchLocal({
        expansionBusy: false,
        activity: (await settings()).paused ? "paused" : "idle",
      });
    }
  }

  async function importAllExpansions({ resume: resumeFromCheckpoint = false } = {}) {
    const tab = await activeCardmarketTab(["singles-index", "expansion"]);
    if (!tab?.id) {
      const error = new Error(
        "Open Cardmarket Singles first (the page with the Expansion dropdown).",
      );
      error.code = "http";
      throw error;
    }
    const previous = await readStore(local, ["expansionResume"]);
    const saved =
      previous.expansionResume && typeof previous.expansionResume === "object"
        ? previous.expansionResume
        : null;
    if (!resumeFromCheckpoint && saved?.kind === "unmatched-images") {
      const error = new Error(
        "Unmatched listing-image crawl is paused. Press Continue for that crawl first.",
      );
      error.code = "http";
      throw error;
    }
    const resume = resumeFromCheckpoint ? saved : null;
    await patchLocal({
      paused: false,
      expansionBusy: true,
      activity: "crawling-all-sets",
      attention: null,
      expansionNote: resume ? "Continuing from where it left off…" : "Checking already imported sets…",
    });
    const seen = new Set();
    const totals = {
      stored: Number(resume?.totals?.stored) || 0,
      linked: Number(resume?.totals?.linked) || 0,
      unmatched: Number(resume?.totals?.unmatched) || 0,
    };
    try {
      let targets = [];
      let startIndex = 0;
      if (resume?.targets?.length) {
        targets = resume.targets.slice(0, MAX_EXPANSIONS);
        startIndex = Math.min(Math.max(Number(resume.index) || 0, 0), targets.length);
      } else {
        let listed = await driveExpansion(tab.id, "list");
        targets = Array.isArray(listed?.expansions) ? listed.expansions : [];
        if (!targets.length) {
          await driveExpansion(tab.id, "open");
          await humanPause("think");
          listed = await driveExpansion(tab.id, "list");
          targets = Array.isArray(listed?.expansions) ? listed.expansions : [];
        }
        if (!targets.length) {
          const snap = await extractExpansionFromTab(tab);
          targets = Array.isArray(snap?.expansions) ? snap.expansions : [];
        }
        targets = targets.filter((item) => item?.id || classifyUrl(item?.url || "") === "expansion");
        targets = targets.slice(0, MAX_EXPANSIONS);
        if (!targets.length && saved?.targets?.length) {
          targets = saved.targets.slice(0, MAX_EXPANSIONS);
        }
      }
      if (!targets.length) {
        const error = new Error(
          "No expansions found in the filter. Open the Expansion dropdown, then try Import all expansions again.",
        );
        error.code = "http";
        throw error;
      }
      if (resume && resume.index != null && !resume.targets?.length) {
        startIndex = Math.min(Math.max(Number(resume.index) || 0, 0), targets.length);
      }
      if (!resumeFromCheckpoint) {
        startIndex = 0;
      }
      let crawls = await loadImportedCrawls();
      if (!resumeFromCheckpoint) {
        startIndex = firstUnfinishedIndex(targets, crawls);
      }
      const resumeLabel = targets[startIndex]?.name || targets[startIndex]?.id || targets[startIndex]?.url;
      await patchLocal({
        expansionResume: {
          index: startIndex,
          targets,
          totals: { stored: totals.stored, linked: totals.linked, unmatched: totals.unmatched },
          reason: "running",
        },
        expansionNote: startIndex
          ? `Skipping ${startIndex} already imported · resuming at ${resumeLabel || "the next set"}`
          : "Starting from the first expansion…",
      });
      let current = tab;
      let halted = false;
      const startPace = paceProfile((await settings()).expansionPace);
      let nextBreakAt = startIndex + jitter(startPace.breakEveryMin, startPace.breakEveryMax);
      for (let index = startIndex; index < targets.length; index += 1) {
        if ((await settings()).paused) {
          const target = targets[index];
          await pauseAllExpansions({
            reason: "paused",
            index,
            targets,
            totals,
            label: target.name || target.id || target.url,
            tabId: current.id,
          });
          halted = true;
          break;
        }
        const target = targets[index];
        const label = target.name || target.id || target.url;
        const latestCrawls = await loadImportedCrawls();
        if (latestCrawls.length) {
          crawls = latestCrawls;
        }
        if (!(resumeFromCheckpoint && index === startIndex) && crawlAlreadyDone(target, crawls)) {
          await patchLocal({
            expansionNote: `Skipping ${label} (already imported) · ${index + 1}/${targets.length}`,
            lastExpansionImport: {
              skipped: true,
              expansions: targets.length,
              expansionIndex: index + 1,
              stored: totals.stored,
              linked: totals.linked,
              unmatched: totals.unmatched,
            },
            expansionResume: {
              index: index + 1,
              targets,
              totals: { stored: totals.stored, linked: totals.linked, unmatched: totals.unmatched },
              reason: "running",
            },
          });
          continue;
        }
        await patchLocal({
          expansionNote: `Set ${index + 1}/${targets.length}: ${label}`,
          activity: "crawling-all-sets",
        });
        await humanPause("think");
        if ((await settings()).paused) {
          await pauseAllExpansions({ reason: "paused", index, targets, totals, label, tabId: current.id });
          halted = true;
          break;
        }
        await openExpansionInTab(current, target);
        current = (await waitForExpansionPage(current.id)) || (await tabs.get(current.id));
        if ((await settings()).paused) {
          await pauseAllExpansions({ reason: "paused", index, targets, totals, label, tabId: current.id });
          halted = true;
          break;
        }
        if (!tabBlockReason(current) && classifyUrl(current?.url || "") !== "expansion" && target.url) {
          await tabs.update(current.id, { url: target.url, active: true });
          current = (await waitForExpansionPage(current.id)) || (await tabs.get(current.id));
        }
        await humanPause("settle");
        current = (await tabs.get(current.id)) || current;
        if ((await settings()).paused) {
          await pauseAllExpansions({ reason: "paused", index, targets, totals, label, tabId: current.id });
          halted = true;
          break;
        }
        const blocked = tabBlockReason(current);
        if (shouldPauseCrawl(blocked)) {
          await pauseAllExpansions({ reason: blocked, index, targets, totals, label, tabId: current.id });
          halted = true;
          break;
        }
        if (classifyUrl(current?.url || "") !== "expansion") {
          continue;
        }
        const crawled = await crawlExpansionPages(current, { crawl: true, seen, totals });
        current = crawled.current || current;
        if (shouldPauseCrawl(crawled.lastResult?.stopped)) {
          await pauseAllExpansions({
            reason: crawled.lastResult.stopped,
            index,
            targets,
            totals,
            label,
            tabId: current.id,
          });
          halted = true;
          break;
        }
        try {
          await request("/cardmarket/helper/expansion-import", {
            method: "POST",
            body: {
              page_url: current.url || target.url || "",
              products: [],
              source: "crawl",
              complete: true,
              expansion_id: String(target.id || ""),
              expansion: String(target.name || ""),
            },
          });
          crawls.push({
            complete: true,
            key: String(target.id || target.name || ""),
            expansion: String(target.name || ""),
            expansion_id: String(target.id || ""),
          });
        } catch {
          /* this run still continues; skip list updates on next Import all */
        }
        await patchLocal({
          lastExpansionImport: {
            ...crawled.lastResult,
            expansions: targets.length,
            expansionIndex: index + 1,
            productsSeen: seen.size,
          },
          expansionResume: {
            index: index + 1,
            targets,
            totals: { stored: totals.stored, linked: totals.linked, unmatched: totals.unmatched },
            reason: "running",
          },
          expansionNote:
            `Set ${index + 1}/${targets.length}: ${label} · stored ${totals.stored} · ` +
            `linked ${totals.linked} · unmatched ${totals.unmatched}`,
        });
        if (index + 1 < targets.length) {
          const pace = paceProfile((await settings()).expansionPace);
          if (pace.setMax) {
            const finished = index + 1;
            if (finished >= nextBreakAt) {
              nextBreakAt = finished + jitter(pace.breakEveryMin, pace.breakEveryMax);
              await patchLocal({
                expansionNote: `Short browse pause after ${finished} sets · stored ${totals.stored} URLs.`,
              });
              await humanPause("break");
            } else {
              await humanPause("set");
            }
          }
        }
      }
      if (!halted) {
        await patchLocal({
          expansionResume: null,
          expansionNote:
            `All sets: stored ${totals.stored} URLs · linked ${totals.linked} · unmatched ${totals.unmatched}. ` +
            "Then run ./scripts/catalogue-all.sh to download scans and match remaining URLs.",
        });
      }
      return totals;
    } finally {
      await patchLocal({ expansionBusy: false, activity: (await settings()).paused ? "paused" : "idle" });
    }
  }

  async function recoverStuckExpansion() {
    const stored = await readStore(local, [
      "expansionBusy",
      "expansionResume",
      "lastExpansionImport",
    ]);
    if (!stored.expansionBusy) {
      return;
    }
    const last = stored.lastExpansionImport || {};
    const resume =
      stored.expansionResume && typeof stored.expansionResume === "object" ? stored.expansionResume : {};
    if (resume.kind === "unmatched-images") {
      await patchLocal({
        expansionBusy: false,
        paused: true,
        activity: "paused",
        attention: "Pass Cloudflare, then press Continue",
        expansionResume: {
          kind: "unmatched-images",
          after: resume.after || "",
          totals: {
            stored: Number(resume.totals?.stored) || 0,
            skipped: Number(resume.totals?.skipped) || 0,
            failed: Number(resume.totals?.failed) || 0,
          },
          reason: resume.reason || "challenge",
        },
        expansionNote: `Paused unmatched listing images after ${resume.after || "start"}. Pass Cloudflare, then press Continue.`,
      });
      return;
    }
    const index = Number.isFinite(Number(resume.index))
      ? Number(resume.index)
      : Math.max((Number(last.expansionIndex) || 1) - 1, 0);
    await patchLocal({
      expansionBusy: false,
      paused: true,
      activity: "paused",
      attention: "Pass Cloudflare, then press Continue",
      expansionResume: {
        index,
        targets: Array.isArray(resume.targets) ? resume.targets : null,
        totals: {
          stored: Number(resume.totals?.stored ?? last.stored) || 0,
          linked: Number(resume.totals?.linked ?? last.linked) || 0,
          unmatched: Number(resume.totals?.unmatched ?? last.unmatched) || 0,
        },
        reason: resume.reason || "challenge",
      },
      expansionNote: `Paused at set ${index + 1}. Pass Cloudflare, then press Continue. Kept stored URLs.`,
    });
  }

  async function openHelperTab() {
    const stored = await readStore(local, ["currentJob"]);
    const url = stored.currentJob?.url || "https://www.cardmarket.com/en/Pokemon";
    let tab = await helperTab();
    if (!tab) {
      tab = await createHelperTab(url, { active: true });
    } else {
      await tabs.update(tab.id, { active: true });
    }
    await patchLocal({ helperTabClosed: false, attention: null });
  }

  async function setPaused(paused) {
    const stored = await readStore(local, ["attention", "pendingResult", "currentJob", "expansionResume"]);
    await patchLocal({ paused, attention: paused ? stored.attention : null });
    if (paused) {
      if (stored.pendingResult) {
        await uploadPending();
      } else if (stored.currentJob?.phase === "loading") {
        await releaseCurrent("paused");
      }
      await publish({ activity: "paused" });
      return;
    }
    await patchLocal({ helperTabClosed: false, attention: null, activity: "idle" });
    if (stored.expansionResume?.kind === "unmatched-images") {
      await importUnmatchedImages({ resume: true });
      return;
    }
    if (stored.expansionResume && (stored.expansionResume.targets?.length || stored.expansionResume.index != null)) {
      await importAllExpansions({ resume: true });
      return;
    }
    await tick();
  }

  async function changeServer(apiBase) {
    await releaseCurrent("server-change");
    const next = String(apiBase || DEFAULT_API).replace(/\/$/, "");
    const stored = await readStore(local, ["helperTokens", "helperToken"]);
    const byServer =
      stored.helperTokens && typeof stored.helperTokens === "object" ? { ...stored.helperTokens } : {};
    await patchLocal({
      apiBase: next,
      helperToken: String(byServer[next] || ""),
      currentJob: null,
      pendingResult: null,
    });
    await tick();
  }

  async function changeToken(helperToken) {
    const { apiBase } = await settings();
    const stored = await readStore(local, ["helperTokens"]);
    const byServer =
      stored.helperTokens && typeof stored.helperTokens === "object" ? { ...stored.helperTokens } : {};
    const token = String(helperToken || "");
    if (token) {
      byServer[apiBase] = token;
    } else {
      delete byServer[apiBase];
    }
    await patchLocal({ helperToken: token, helperTokens: byServer });
    await tick();
  }

  async function onMessage(message, sender) {
    if (message?.type === "extract-result") {
      return bindExtract(message, sender);
    }
    if (message?.type === "page-cleared") {
      await maybeResumeAfterChallenge(sender?.tab || {});
      return snapshot();
    }
    if (message?.type === "get-status") {
      return snapshot();
    }
    if (message?.type === "pause") {
      await setPaused(true);
      return snapshot();
    }
    if (message?.type === "resume") {
      await setPaused(false);
      return snapshot();
    }
    if (message?.type === "poll" || message?.type === "check-connection") {
      await tick();
      return snapshot();
    }
    if (message?.type === "open-helper-tab") {
      await openHelperTab();
      return snapshot();
    }
    if (message?.type === "set-settings") {
      if (message.apiBase) {
        await changeServer(message.apiBase);
      }
      if (message.helperToken != null) {
        await changeToken(message.helperToken);
      }
      if (message.ntfyTopic != null && String(message.ntfyTopic).trim()) {
        await patchLocal({ ntfyTopic: String(message.ntfyTopic).trim() });
      }
      if (message.expansionPace != null) {
        await patchLocal({ expansionPace: normalizePace(message.expansionPace) });
      }
      if (message.saveUnmatchedImage != null) {
        await patchLocal({ saveUnmatchedImage: Boolean(message.saveUnmatchedImage) });
      }
      return snapshot();
    }
    if (message?.type === "notify-test") {
      await notifyPhone("Test ping from Scanapp helper. Cloudflare alerts will look like this.");
      return snapshot();
    }
    if (message?.type === "map-url") {
      try {
        const mapped = await mapCurrentUrl(message.url, message.cardId);
        return { ok: true, ...mapped };
      } catch (error) {
        return { ok: false, error: String(error?.message || error) };
      }
    }
    if (message?.type === "save-unmatched-image") {
      try {
        const stored = await saveUnmatchedListingImage(message.url, message.name);
        return { ok: true, ...stored };
      } catch (error) {
        return { ok: false, error: String(error?.message || error) };
      }
    }
    if (
      message?.type === "import-expansion-page" ||
      message?.type === "import-expansion-set" ||
      message?.type === "import-expansion-all" ||
      message?.type === "import-unmatched-images"
    ) {
      try {
        if (message.type === "import-unmatched-images") {
          if ((await readStore(local, ["expansionBusy"])).expansionBusy) {
            return snapshot();
          }
          await importUnmatchedImages();
        } else if (message.type === "import-expansion-all") {
          await importAllExpansions();
        } else {
          await importExpansion({
            crawl: message.type === "import-expansion-set",
          });
        }
        return snapshot();
      } catch (error) {
        const note = String(error?.message || error);
        await patchLocal({
          expansionBusy: false,
          activity: "idle",
          expansionNote: note,
        });
        return { ...(await snapshot()), error: note };
      }
    }
    return undefined;
  }

  async function liveTabState(tab) {
    const fallback = {
      title: tab?.title || "",
      url: tab?.url || "",
      ready: false,
      cf: false,
      hasListingImage: false,
      inspected: false,
    };
    if (!tab?.id || typeof scripting?.executeScript !== "function") {
      return fallback;
    }
    try {
      const injected = await withTimeout(
        scripting.executeScript({
          target: { tabId: tab.id },
          args: [CHALLENGE_SELECTOR],
          func: inspectProductPage,
        }),
        2_500,
      );
      const result = Array.isArray(injected) ? injected[0]?.result : injected?.result;
      if (!result) {
        return fallback;
      }
      return {
        title: result.title || fallback.title,
        url: result.url || fallback.url,
        ready: Boolean(result.ready),
        cf: Boolean(result.cf),
        hasListingImage: Boolean(result.hasListingImage || result.listingSrc),
        listingSrc: String(result.listingSrc || ""),
        listingReady: Boolean(result.listingReady),
        inspected: true,
      };
    } catch {
      return { ...fallback, cf: true };
    }
  }

  async function challengePageCleared(tab) {
    if (!tab?.url && !tab?.id) {
      return false;
    }
    const live = await liveTabState(tab);
    const title = String(live.title || tab?.title || "").trim();
    const url = live.url || tab?.url || "";
    if (challengeTitle(title) || live.cf) {
      return false;
    }
    if (live.ready && url) {
      return true;
    }
    if (!title) {
      return false;
    }
    if (tabBlockReason({ ...tab, title, url })) {
      return false;
    }
    const kind = classifyUrl(url);
    const resumeKind = (await readStore(local, ["expansionResume"])).expansionResume?.kind;
    if (resumeKind === "unmatched-images") {
      return kind === "product" && Boolean(live.hasListingImage) && !live.cf;
    }
    return kind === "expansion" || kind === "singles-index";
  }

  async function maybeResumeAfterChallenge(tab) {
    const stored = await readStore(local, ["paused", "expansionBusy", "expansionResume"]);
    if (!stored.paused || stored.expansionBusy) {
      return false;
    }
    if (stored.expansionResume?.reason !== "challenge") {
      return false;
    }
    if (!(await challengePageCleared(tab))) {
      return false;
    }
    await patchLocal({ expansionNote: "Cloudflare passed — continuing the crawl…" });
    await setPaused(false);
    return true;
  }

  async function maybeResumeFromOpenTabs() {
    const stored = await readStore(local, ["paused", "expansionBusy", "expansionResume"]);
    if (!stored.paused || stored.expansionBusy || stored.expansionResume?.reason !== "challenge") {
      return false;
    }
    let found = [];
    try {
      found = await tabs.query({
        url: ["https://www.cardmarket.com/*", "https://cardmarket.com/*"],
      });
    } catch {
      found = [];
    }
    for (const tab of found || []) {
      if (await maybeResumeAfterChallenge(tab)) {
        return true;
      }
    }
    return false;
  }

  async function watchPausedChallenge(tabId) {
    for (let step = 0; step < CHALLENGE_WATCH_TICKS; step += 1) {
      await wait(CHALLENGE_WATCH_MS);
      const stored = await readStore(local, ["paused", "expansionBusy", "expansionResume"]);
      if (!stored.paused || stored.expansionBusy || stored.expansionResume?.reason !== "challenge") {
        return;
      }
      if (tabId) {
        try {
          const tab = await tabs.get(tabId);
          if (await maybeResumeAfterChallenge(tab)) {
            return;
          }
        } catch {
          /* tab closed */
        }
      }
      if (await maybeResumeFromOpenTabs()) {
        return;
      }
    }
  }

  async function onTabRemoved(tabId) {
    const stored = await readStore(session, ["helperTabId"]);
    if (stored.helperTabId !== tabId) {
      return;
    }
    await writeStore(session, { helperTabId: null, helperDocumentId: null });
  }

  async function onTabUpdated(tabId, info, tab) {
    const url = tab?.url || info.url;
    const merged = { ...tab, id: tabId, url, title: tab?.title || info.title };
    const localState = await readStore(local, ["currentJob", "paused", "expansionResume"]);
    if (localState.paused && localState.expansionResume?.reason === "challenge") {
      if (!info.status || info.status === "complete" || info.title) {
        await maybeResumeAfterChallenge(merged);
      }
      return;
    }
    const job = localState.currentJob;
    if (!job || localState.paused || !url) {
      return;
    }
    if (!(finalUrlAllowed(job.url, url) || normalizeUrl(url) === normalizeUrl(job.url))) {
      return;
    }
    if (tab?.documentId) {
      await writeStore(session, { helperDocumentId: tab.documentId });
    }
    await adoptTab({ id: tabId, documentId: tab?.documentId });
    if (info.status === "complete" || classifyUrl(url) === "product") {
      await tick();
    }
  }

  return {
    wake(reason) {
      return enqueue(async () => {
        if (reason === "startup") {
          await writeStore(session, { helperTabId: null, helperDocumentId: null });
        }
        await recoverStuckExpansion();
        await tick();
      });
    },
    handleMessage(message, sender) {
      if (message?.type === "get-status") {
        return snapshot();
      }
      if (message?.type === "map-status") {
        return mapStatus();
      }
      if (message?.type === "expansion-status") {
        return snapshot();
      }
      if (message?.type === "pause") {
        return (async () => {
          await patchLocal({
            paused: true,
            activity: "paused",
            attention: "Pass Cloudflare, then press Continue",
          });
          return snapshot();
        })();
      }
      return enqueue(() => onMessage(message, sender));
    },
    tabRemoved(tabId) {
      return enqueue(() => onTabRemoved(tabId));
    },
    tabUpdated(tabId, info, tab) {
      return enqueue(() => onTabUpdated(tabId, info, tab));
    },
    installAlarms: ensureAlarms,
    snapshot,
    enqueue,
    _tick: tick,
    _bindExtract: bindExtract,
  };
}

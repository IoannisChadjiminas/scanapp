import {
  DEFAULT_API,
  IDLE_ALARM,
  IDLE_PERIOD_MINUTES,
  MAX_RECENT_FAILURES,
  NAV_SPACING_MS,
  PAGE_DEADLINE_MS,
  PARSER_VERSION,
  WAIT_ALARM,
} from "./constants.js";
import { classifyUrl, finalUrlAllowed, normalizeUrl } from "./url.js";

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
  now = () => Date.now(),
  randomId = () => `${now()}-${Math.random().toString(16).slice(2)}`,
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
    const stored = await readStore(local, ["apiBase", "helperToken", "paused"]);
    return {
      apiBase: String(stored.apiBase || DEFAULT_API).replace(/\/$/, ""),
      helperToken: String(stored.helperToken || ""),
      paused: Boolean(stored.paused),
    };
  }

  async function request(path, { method = "GET", body } = {}) {
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
    let response;
    try {
      response = await fetchImpl(`${apiBase}/api/v1${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      const error = new Error("disconnected");
      error.code = "network";
      error.cause = cause;
      throw error;
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
      const error = new Error(payload.detail || `http ${response.status}`);
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
    await patchLocal({ currentJob: null, currentCard: "" });
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
    if (sender?.tab?.id && sessionState.helperTabId && sender.tab.id !== sessionState.helperTabId) {
      return { ok: false, reason: "wrong-tab" };
    }
    if (
      sessionState.helperDocumentId &&
      sender?.documentId &&
      sender.documentId !== sessionState.helperDocumentId
    ) {
      return { ok: false, reason: "wrong-document" };
    }
    const finalUrl = normalizeUrl(message.url || sender?.tab?.url || "");
    const kind = classifyUrl(finalUrl);
    if (kind === "login" || kind === "challenge" || message.outcome === "challenge") {
      await request("/cardmarket/helper/fail", {
        method: "POST",
        body: {
          job_id: job.id,
          claim_token: job.claimToken,
          reason: "challenge",
        },
      }).catch(() => undefined);
      await patchLocal({
        paused: true,
        attention: "Cardmarket needs attention",
        activity: "needs_attention",
        currentJob: job,
      });
      return { ok: false, reason: "challenge" };
    }
    if (message.outcome === "wrong_product" || kind === "search" || !finalUrlAllowed(job.url, finalUrl)) {
      await failCurrent("wrong_product", true);
      return { ok: false, reason: "wrong-product" };
    }
    if (message.outcome === "unrecognized") {
      await failCurrent("parser", false);
      await scheduleWait(NAV_SPACING_MS);
      return { ok: false, reason: "parser" };
    }
    const empty = message.outcome === "empty";
    const prices = Array.isArray(message.prices) ? message.prices : [];
    if (!empty && !prices.length) {
      await failCurrent("parser", false);
      return { ok: false, reason: "parser" };
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
    if (!tabs.sendMessage || !tab?.id) {
      return null;
    }
    try {
      return await tabs.sendMessage(
        tab.id,
        {
          type: "extract",
          requestId: job.requestId,
          jobId: job.id,
          expectedUrl: job.url,
        },
        tab.documentId ? { documentId: tab.documentId } : undefined,
      );
    } catch {
      return null;
    }
  }

  async function loadJob(job) {
    await publish({ activity: "fetching", currentCard: job.card_id || job.url });
    let tab = await helperTab();
    const target = job.url;
    const stored = await readStore(local, ["lastNavigationAt", "helperTabClosed", "paused"]);
    if (stored.helperTabClosed && stored.paused) {
      await publish({ activity: "needs_attention", attention: "Helper tab closed" });
      return;
    }
    if (!tab) {
      tab = await createHelperTab(target, { active: false });
      await patchLocal({ lastNavigationAt: now(), currentJob: { ...job, phase: "loading", loadStartedAt: now() } });
      await scheduleWait(PAGE_DEADLINE_MS);
      return;
    }
    const currentUrl = tab.url || "";
    const alreadyThere =
      normalizeUrl(currentUrl) === normalizeUrl(target) || classifyUrl(currentUrl) === "product";
    if (!alreadyThere) {
      const wait = (stored.lastNavigationAt || 0) + NAV_SPACING_MS - now();
      if (wait > 0) {
        await scheduleWait(wait);
        return;
      }
      await tabs.update(tab.id, { url: target, active: false });
      await patchLocal({
        lastNavigationAt: now(),
        currentJob: { ...job, phase: "loading", loadStartedAt: now() },
      });
      await scheduleWait(PAGE_DEADLINE_MS);
      return;
    }
    const kind = classifyUrl(currentUrl);
    if (kind === "login" || kind === "challenge") {
      await bindExtract({ type: "extract-result", requestId: job.requestId, jobId: job.id, outcome: "challenge", url: currentUrl }, { tab });
      return;
    }
    if (kind === "search" || kind === "other") {
      await bindExtract({ type: "extract-result", requestId: job.requestId, jobId: job.id, outcome: "wrong_product", url: currentUrl }, { tab });
      return;
    }
    if (kind === "pokemontcg") {
      if (now() - (job.loadStartedAt || now()) > PAGE_DEADLINE_MS) {
        await failCurrent("loading");
        return;
      }
      await scheduleWait(1000);
      return;
    }
    const result = await extractFromTab(tab, job);
    if (result?.outcome) {
      await bindExtract({ type: "extract-result", ...result, requestId: job.requestId, jobId: job.id }, { tab, documentId: tab.documentId });
      return;
    }
    if (now() - (job.loadStartedAt || now()) > PAGE_DEADLINE_MS) {
      await failCurrent("loading");
      return;
    }
    await patchLocal({ currentJob: { ...job, phase: "extracting" } });
    await scheduleWait(1000);
  }

  async function tick() {
    await ensureAlarms();
    const { helperToken, paused, apiBase } = await settings();
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
    const stored = await readStore(local, ["currentJob"]);
    let job = stored.currentJob;
    if (job?.id && job.claimToken) {
      try {
        const recovered = await request("/cardmarket/helper/claim", {
          method: "POST",
          body: { job_id: job.id, claim_token: job.claimToken },
        });
        if (!recovered?.id || recovered.id !== job.id) {
          await patchLocal({ currentJob: null, pendingResult: null });
          job = null;
        } else {
          await request("/cardmarket/helper/renew", {
            method: "POST",
            body: { job_id: job.id, claim_token: job.claimToken },
          }).catch(() => undefined);
          job = { ...job, ...recovered, claimToken: recovered.claim_token || job.claimToken };
          await patchLocal({ currentJob: job, currentCard: job.card_id || job.url });
        }
      } catch (error) {
        if (error.code === "claim") {
          await patchLocal({ currentJob: null, pendingResult: null });
          job = null;
        } else {
          return;
        }
      }
    }
    if (!job) {
      const claimed = await request("/cardmarket/helper/claim", { method: "POST", body: {} });
      if (!claimed?.id || claimed.status === "idle") {
        await publish({ activity: "idle", currentCard: "", queued: claimed?.queued || 0 });
        return;
      }
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
      await patchLocal({ currentJob: job, currentCard: job.card_id || job.url });
    }
    await loadJob(job);
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
    await patchLocal({ paused, attention: paused ? (await readStore(local, ["attention"])).attention : null });
    if (paused) {
      const stored = await readStore(local, ["pendingResult", "currentJob"]);
      if (stored.pendingResult) {
        await uploadPending();
      } else if (stored.currentJob?.phase === "loading") {
        await releaseCurrent("paused");
      }
      await publish({ activity: "paused" });
      return;
    }
    await patchLocal({ helperTabClosed: false, attention: null, activity: "idle" });
    await enqueue(tick);
  }

  async function changeServer(apiBase) {
    await releaseCurrent("server-change");
    await patchLocal({ apiBase: String(apiBase || DEFAULT_API).replace(/\/$/, ""), currentJob: null, pendingResult: null });
    await enqueue(tick);
  }

  async function changeToken(helperToken) {
    await patchLocal({ helperToken: String(helperToken || "") });
    await enqueue(tick);
  }

  async function onMessage(message, sender) {
    if (message?.type === "extract-result") {
      return bindExtract(message, sender);
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
    if (message?.type === "check-connection") {
      await enqueue(tick);
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
      return snapshot();
    }
    return undefined;
  }

  async function onTabRemoved(tabId) {
    const stored = await readStore(session, ["helperTabId"]);
    if (stored.helperTabId !== tabId) {
      return;
    }
    const localState = await readStore(local, ["currentJob", "paused"]);
    await writeStore(session, { helperTabId: null, helperDocumentId: null });
    if (localState.currentJob && !localState.paused) {
      await abandonHelperTab("Helper tab closed");
      await releaseCurrent("closed_tab");
    }
  }

  async function onTabUpdated(tabId, info, tab) {
    const stored = await readStore(session, ["helperTabId"]);
    if (stored.helperTabId !== tabId) {
      return;
    }
    if (tab?.documentId) {
      await writeStore(session, { helperDocumentId: tab.documentId });
    }
    const localState = await readStore(local, ["currentJob", "paused"]);
    const job = localState.currentJob;
    if (!job || localState.paused) {
      return;
    }
    const url = tab?.url || info.url;
    if (!url) {
      return;
    }
    const kind = classifyUrl(url);
    const expected = classifyUrl(job.url);
    const allowed =
      kind === "pokemontcg" ||
      kind === "product" ||
      (expected === "pokemontcg" && kind === "product");
    if (info.url && !allowed && kind !== "invalid") {
      await abandonHelperTab("Helper tab navigated away");
      await releaseCurrent("navigated_away");
      return;
    }
    if (info.status === "complete" || kind === "product") {
      await enqueue(tick);
    }
  }

  return {
    wake(reason) {
      return enqueue(async () => {
        if (reason === "startup") {
          await writeStore(session, { helperTabId: null, helperDocumentId: null });
        }
        await tick();
      });
    },
    handleMessage(message, sender) {
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

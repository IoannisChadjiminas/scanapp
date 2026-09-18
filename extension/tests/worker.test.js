import assert from "node:assert/strict";
import test from "node:test";

import { createWorker } from "../lib/worker.js";

const GENGAR =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102";
const PIKACHU =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008";

function memoryStore(initial = {}) {
  const data = { ...initial };
  return {
    async get(keys) {
      if (keys == null) {
        return { ...data };
      }
      const list = Array.isArray(keys)
        ? keys
        : typeof keys === "string"
          ? [keys]
          : Object.keys(keys);
      const out = {};
      for (const key of list) {
        out[key] = data[key];
      }
      return out;
    },
    async set(values) {
      Object.assign(data, values);
    },
    async remove(keys) {
      for (const key of [].concat(keys)) {
        delete data[key];
      }
    },
  };
}

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function createHarness({ extract, scripting, claimJobs } = {}) {
  const local = memoryStore({
    apiBase: "http://127.0.0.1:8000",
    helperToken: "helper.token",
  });
  const session = memoryStore();
  const tabs = new Map();
  let tabSeq = 1;
  let activeTab = 99;
  const claims = [];
  const completes = [];
  const createdTabs = [];
  const fails = [];
  let claimIndex = 0;
  const fetchImpl = async (url, init = {}) => {
    const path = new URL(url).pathname;
    const body = init.body ? JSON.parse(init.body) : {};
    if (path.endsWith("/cardmarket/helper/status")) {
      return jsonResponse({ queued: 1, helper_ready: true, helper_online: true });
    }
    if (path.endsWith("/cardmarket/helper/claim")) {
      if (!body.job_id && !claims.length) {
        claims.push(body);
      }
      if (claimJobs?.length) {
        const payload = claimJobs[Math.min(claimIndex, claimJobs.length - 1)];
        claimIndex += 1;
        return jsonResponse(payload);
      }
      return jsonResponse({
        id: "job-1",
        url: GENGAR,
        card_id: "gengar",
        claim_token: "claim-1",
        claim_expires_at: "2099-01-01T00:00:00Z",
        product_identity: "singles:sm9102",
        status: "claimed",
      });
    }
    if (path.endsWith("/cardmarket/helper/renew")) {
      return jsonResponse({ id: "job-1", claim_token: "claim-1", url: GENGAR, status: "claimed" });
    }
    if (path.endsWith("/cardmarket/helper/complete")) {
      completes.push(body);
      return jsonResponse({ status: "done", prices: body.prices || [], idempotent: completes.length > 1 });
    }
    if (path.endsWith("/cardmarket/helper/fail")) {
      fails.push(body);
      return jsonResponse({ status: "pending" });
    }
    if (path.endsWith("/cardmarket/helper/release")) {
      return jsonResponse({ status: "pending" });
    }
    return jsonResponse({ detail: "missing" }, 404);
  };
  const updates = [];
  let clock = 1_000_000;
  const tabApi = {
    async create({ url, active }) {
      const tab = { id: tabSeq++, url, active: Boolean(active), documentId: `doc-${tabSeq}` };
      tabs.set(tab.id, tab);
      createdTabs.push(tab);
      if (active) {
        activeTab = tab.id;
      }
      return tab;
    },
    async get(id) {
      const tab = tabs.get(id);
      if (!tab) {
        throw new Error("missing tab");
      }
      return tab;
    },
    async query() {
      return [...tabs.values()];
    },
    async update(id, props) {
      const tab = tabs.get(id);
      Object.assign(tab, props);
      updates.push({ id, ...props });
      if (props.active) {
        activeTab = id;
      }
      return tab;
    },
    async sendMessage(_id, message, options) {
      if (options?.documentId && extract?.requireNoDocumentId) {
        throw new Error("no receiver");
      }
      if (extract) {
        return extract(message);
      }
      return {
        outcome: "offers",
        url: GENGAR,
        prices: [{ label: "NM", amount: 10, currency: "EUR" }],
        observedAt: "2026-09-17T12:00:00Z",
        parserVersion: "offers-v1",
        sampledOfferCount: 1,
      };
    },
  };
  const worker = createWorker({
    local,
    session,
    fetchImpl,
    tabs: tabApi,
    scripting,
    alarms: { create: async () => undefined },
    now: () => clock,
    randomId: () => "req-1",
  });
  return {
    worker,
    local,
    session,
    claims,
    completes,
    fails,
    createdTabs,
    tabs,
    updates,
    advance: (ms) => {
      clock += ms;
    },
    activeTab: () => activeTab,
  };
}

test("overlapping wake events claim only one job", async () => {
  const { worker, claims } = createHarness();
  await Promise.all([worker.wake("alarm"), worker.wake("popup"), worker.wake("startup")]);
  assert.equal(claims.length, 1);
});

test("opens the claimed product immediately even after a recent navigation", async () => {
  const { worker, session, local, tabs, updates, createdTabs } = createHarness();
  tabs.set(7, { id: 7, url: PIKACHU, documentId: "doc-7" });
  await session.set({ helperTabId: 7 });
  await local.set({ lastNavigationAt: 1_000_000 });
  await worker.handleMessage({ type: "poll" });
  assert.equal(createdTabs.length, 0);
  assert.equal(updates.some((item) => item.url === GENGAR && item.active === true), true);
});

test("opens Cardmarket in the foreground by itself", async () => {
  const { worker, createdTabs, activeTab } = createHarness();
  await worker.wake("alarm");
  assert.equal(createdTabs.length, 1);
  assert.equal(createdTabs[0].active, true);
  assert.equal(createdTabs[0].url, GENGAR);
  assert.equal(activeTab(), createdTabs[0].id);
});

test("unrecognized extract waits instead of failing", async () => {
  const { worker, fails } = createHarness({
    extract: async () => ({
      outcome: "unrecognized",
      url: GENGAR,
      prices: [],
    }),
  });
  await worker.wake("alarm");
  await worker.wake("alarm");
  assert.equal(fails.length, 0);
});

test("parser fail waits until the page deadline", async () => {
  const { worker, fails, advance } = createHarness({
    extract: async () => ({
      outcome: "unrecognized",
      url: GENGAR,
      prices: [],
    }),
  });
  await worker.wake("alarm");
  advance(61_000);
  await worker.wake("alarm");
  assert.equal(fails.length, 1);
  assert.equal(fails[0].reason, "parser");
});

test("delayed extract from another card is rejected", async () => {
  const { worker } = createHarness();
  await worker.wake("alarm");
  const result = await worker.handleMessage(
    {
      type: "extract-result",
      requestId: "old-card",
      jobId: "job-a",
      url: PIKACHU,
      outcome: "offers",
      prices: [{ label: "NM", amount: 3, currency: "EUR" }],
    },
    { tab: { id: 1 } },
  );
  assert.equal(result.ok, false);
  assert.equal(result.reason, "stale-message");
});

test("lost upload acknowledgement retries the same submission id", async () => {
  const { worker, completes, local } = createHarness();
  await worker.wake("alarm");
  await local.set({
    pendingResult: {
      job_id: "job-1",
      claim_token: "claim-1",
      submission_id: "same-sub",
      url: GENGAR,
      prices: [{ label: "NM", amount: 10, currency: "EUR" }],
      empty: false,
    },
  });
  await worker.wake("alarm");
  await worker.wake("alarm");
  const ids = completes.map((item) => item.submission_id);
  assert.ok(ids.includes("same-sub"));
  assert.equal(ids.filter((item) => item === "same-sub").length >= 1, true);
});

test("pause persists and stops new claims", async () => {
  const { worker, claims, local } = createHarness();
  await worker.handleMessage({ type: "pause" });
  const before = claims.length;
  await worker.wake("alarm");
  assert.equal(claims.length, before);
  const stored = await local.get("paused");
  assert.equal(stored.paused, true);
});

test("closing a product tab does not pause the helper", async () => {
  const { worker, tabs, local } = createHarness();
  tabs.set(50, { id: 50, url: GENGAR, documentId: "doc-50" });
  await worker.wake("alarm");
  await worker.tabRemoved(50);
  const stored = await local.get(["paused", "attention"]);
  assert.equal(Boolean(stored.paused), false);
});

test("status snapshot is not blocked by a hung API", async () => {
  const local = memoryStore({
    apiBase: "https://staging-scan.auctaro.com",
    helperToken: "helper.token",
    connection: "disconnected",
  });
  const worker = createWorker({
    local,
    session: memoryStore(),
    fetchImpl: () => new Promise(() => {}),
    tabs: {
      get: async () => {
        throw new Error("missing");
      },
    },
    alarms: { create: async () => undefined },
  });
  void worker.wake("startup");
  const status = await worker.handleMessage({ type: "get-status" });
  assert.equal(status.helperToken, "helper.token");
  assert.equal(status.apiBase, "https://staging-scan.auctaro.com");
});

test("service worker init can open a foreground helper tab", async () => {
  const { worker, createdTabs } = createHarness();
  await worker.wake("alarm");
  await worker.wake("init");
  assert.equal(createdTabs.length, 1);
  assert.equal(createdTabs[0].active, true);
});

test("does not rewrite a different product tab", async () => {
  const { worker, tabs, createdTabs } = createHarness();
  tabs.set(50, { id: 50, url: PIKACHU, documentId: "doc-50" });
  await worker.wake("alarm");
  assert.equal(tabs.get(50).url, PIKACHU);
  assert.equal(createdTabs.length, 1);
  assert.equal(createdTabs[0].url, GENGAR);
  assert.equal(createdTabs[0].active, true);
});

test("extract retries without documentId", async () => {
  const { worker, tabs, completes } = createHarness({
    extract: Object.assign(
      async () => ({
        outcome: "offers",
        url: GENGAR,
        prices: [{ label: "NM", amount: 10, currency: "EUR" }],
        observedAt: "2026-09-17T12:00:00Z",
        parserVersion: "offers-v1",
        sampledOfferCount: 1,
      }),
      { requireNoDocumentId: true },
    ),
  });
  tabs.set(50, { id: 50, url: GENGAR, documentId: "doc-50" });
  await worker.wake("alarm");
  assert.equal(completes.length, 1);
});

test("waits on the foreground tab when extract is not ready", async () => {
  const { worker, createdTabs, local } = createHarness({
    extract: async () => {
      throw new Error("no receiver");
    },
  });
  await worker.wake("alarm");
  const stored = await local.get(["activity", "recentFailures"]);
  assert.equal(createdTabs.length, 1);
  assert.equal(createdTabs[0].active, true);
  assert.equal(stored.activity, "fetching");
  assert.equal(Array.isArray(stored.recentFailures) ? stored.recentFailures.length : 0, 0);
});

test("reads listings after a product tab opens", async () => {
  const { worker, tabs, completes } = createHarness();
  await worker.wake("alarm");
  assert.equal(completes.length, 0);
  const tab = { id: 50, url: GENGAR, documentId: "doc-50" };
  tabs.set(50, tab);
  await worker.tabUpdated(50, { status: "complete", url: GENGAR }, tab);
  assert.equal(completes.length, 1);
});

test("reads listings through injected extract", async () => {
  const { worker, completes, createdTabs } = createHarness({
    extract: async () => {
      throw new Error("content script missing");
    },
    scripting: {
      executeScript: async ({ files } = {}) => {
        if (files?.[0] === "inject-extract.js") {
          return [
            {
              result: {
                outcome: "offers",
                url: GENGAR,
                prices: [{ label: "NM", amount: 4, currency: "EUR" }],
                observedAt: "2026-09-18T07:00:00Z",
                parserVersion: "offers-v1",
                sampledOfferCount: 1,
              },
            },
          ];
        }
        return [{ result: null }];
      },
    },
  });
  await worker.wake("alarm");
  const tab = createdTabs[0];
  await worker.tabUpdated(tab.id, { status: "complete", url: GENGAR }, tab);
  assert.equal(completes.length, 1);
  assert.equal(completes[0].prices[0].amount, 4);
});

test("uses an already open product tab instead of creating one", async () => {
  const { worker, createdTabs, tabs, session, completes } = createHarness();
  tabs.set(50, { id: 50, url: GENGAR, documentId: "doc-50" });
  await worker.wake("alarm");
  assert.equal(createdTabs.length, 0);
  const stored = await session.get("helperTabId");
  assert.equal(stored.helperTabId, 50);
  assert.equal(completes.length, 1);
});

test("navigates the helper tab to the newly scanned card", async () => {
  const { worker, session, tabs, updates } = createHarness({
    extract: async () => ({
      outcome: "unrecognized",
      url: PIKACHU,
      prices: [],
    }),
    claimJobs: [
      {
        id: "job-old",
        url: PIKACHU,
        card_id: "pikachu",
        claim_token: "claim-old",
        claim_expires_at: "2099-01-01T00:00:00Z",
        product_identity: "singles:clc008",
        status: "claimed",
      },
      {
        id: "job-new",
        url: GENGAR,
        card_id: "gengar",
        claim_token: "claim-new",
        claim_expires_at: "2099-01-01T00:00:00Z",
        product_identity: "singles:sm9102",
        status: "claimed",
      },
    ],
  });
  tabs.set(7, { id: 7, url: PIKACHU, documentId: "doc-7" });
  await session.set({ helperTabId: 7 });
  await worker.wake("alarm");
  assert.equal(tabs.get(7).url, PIKACHU);
  await worker.wake("alarm");
  assert.equal(tabs.get(7).url, GENGAR);
  assert.equal(
    updates.some((item) => item.url === GENGAR && item.active === true),
    true,
  );
});

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

function createHarness({ extract, scripting, claimJobs, expansionExtract, expansionCrawls } = {}) {
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
  const expansionImports = [];
  const ntfyPosts = [];
  const crawls = [...(expansionCrawls || [])];
  let claimIndex = 0;
  const fetchImpl = async (url, init = {}) => {
    if (String(url).includes("ntfy.sh")) {
      ntfyPosts.push({ url, body: init.body, headers: init.headers });
      return jsonResponse({ id: "ok" });
    }
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
    if (path.endsWith("/cardmarket/helper/map")) {
      return jsonResponse({
        ok: true,
        card_id: body.card_id,
        url: body.url,
        name: "Gengar",
        verified: true,
      });
    }
    if (path.endsWith("/cardmarket/helper/expansion-crawls")) {
      return jsonResponse({ expansions: crawls });
    }
    if (path.endsWith("/cardmarket/helper/expansion-import")) {
      expansionImports.push(body);
      if (body.complete) {
        crawls.push({
          complete: true,
          expansion: body.expansion,
          expansion_id: body.expansion_id,
          key: body.expansion_id || body.expansion,
        });
      }
      const count = Array.isArray(body.products) ? body.products.length : 0;
      return jsonResponse({
        stored: count,
        linked: 0,
        unmatched: count,
        products: count,
        source: body.source,
      });
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
    async query(filter = {}) {
      let list = [...tabs.values()];
      if (filter.active) {
        const focused = list.filter((tab) => tab.active || tab.id === activeTab);
        if (focused.length) {
          list = focused;
        }
      }
      return list;
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
    async reload(id) {
      const tab = tabs.get(id);
      if (!tab) {
        throw new Error("missing tab");
      }
      updates.push({ id, reload: true, url: tab.url, active: true });
      tab.active = true;
      activeTab = id;
      return tab;
    },
    async sendMessage(_id, message, options) {
      if (options?.documentId && extract?.requireNoDocumentId) {
        throw new Error("no receiver");
      }
      if (message?.type === "extract-expansion" && expansionExtract) {
        const tab = tabs.get(_id);
        return expansionExtract(tab);
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
  const scriptApi =
    scripting ||
    (expansionExtract
      ? {
          executeScript: async ({ files, target, func, args } = {}) => {
            if (typeof func === "function") {
              const action = args?.[0];
              const payload = args?.[1] || {};
              const tab = tabs.get(target.tabId);
              if (action === "open") {
                return [{ result: { ok: true, method: "select" } }];
              }
              if (action === "list") {
                const snap = expansionExtract?.(tab) || {};
                return [{ result: { expansions: snap.expansions || [], method: "select" } }];
              }
              if (action === "apply") {
                const next = payload.url;
                if (next && tab) {
                  Object.assign(tab, { url: next, active: true });
                  updates.push({ id: tab.id, url: next, active: true });
                }
                return [{ result: { ok: true, method: "form" } }];
              }
              return [{ result: null }];
            }
            if (files?.[0] === "expansion-extract.js") {
              const tab = tabs.get(target.tabId);
              return [{ result: expansionExtract(tab) }];
            }
            return [{ result: null }];
          },
        }
      : scripting);
  const worker = createWorker({
    local,
    session,
    fetchImpl,
    tabs: tabApi,
    scripting: scriptApi,
    alarms: { create: async () => undefined },
    now: () => clock,
    randomId: () => "req-1",
    wait: async (ms) => {
      clock += ms;
    },
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
    expansionImports,
    ntfyPosts,
    advance: (ms) => {
      clock += ms;
    },
    activeTab: () => activeTab,
  };
}

function productPages(imports) {
  return imports.filter((item) => Array.isArray(item.products) && item.products.length);
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

test("saves the open product URL for the current scan", async () => {
  const { worker, local } = createHarness();
  await local.set({ lastCardId: "extra-gengar", lastCardLabel: "extra-gengar" });
  const mapped = await worker.handleMessage({ type: "map-url", url: GENGAR });
  assert.equal(mapped.ok, true);
  assert.equal(mapped.card_id, "extra-gengar");
  assert.equal(mapped.url, GENGAR);
});

test("imports only the current set-list page", async () => {
  const page = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  const { worker, tabs, expansionImports, createdTabs } = createHarness({
    expansionExtract: () => ({
      pageUrl: page,
      products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
      nextPage: `${page}?site=2`,
    }),
  });
  tabs.set(9, { id: 9, url: page, active: true, documentId: "doc-9" });
  const status = await worker.handleMessage({ type: "import-expansion-page" });
  assert.equal(expansionImports.length, 1);
  assert.equal(expansionImports[0].source, "page");
  assert.equal(expansionImports[0].products[0].url, GENGAR);
  assert.equal(createdTabs.length, 0);
  assert.equal(tabs.get(9).url, page);
  assert.equal(status.expansionBusy, false);
  assert.match(status.expansionNote, /Stored 1/);
});

test("test crawler stores every page in the open set", async () => {
  const page = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  const { worker, tabs, expansionImports, createdTabs, updates } = createHarness({
    expansionExtract: (tab) => {
      const href = tab?.url || page;
      if (String(href).includes("site=2")) {
        return {
          pageUrl: href,
          products: [{ url: PIKACHU, name: "Pikachu" }],
          nextPage: null,
        };
      }
      return {
        pageUrl: href,
        products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
        nextPage: `${page}?site=2`,
      };
    },
  });
  tabs.set(9, { id: 9, url: page, active: true, documentId: "doc-9" });
  await worker.handleMessage({ type: "import-expansion-set" });
  const pageImports = expansionImports.filter((item) => Array.isArray(item.products) && item.products.length && !item.replace);
  assert.equal(pageImports.length, 2);
  assert.equal(pageImports[0].source, "crawl");
  assert.equal(pageImports[1].source, "crawl");
  assert.equal(pageImports[0].products[0].url, GENGAR);
  assert.equal(pageImports[1].products[0].url, PIKACHU);
  const replaced = expansionImports.filter((item) => item.replace);
  assert.equal(replaced.length, 1);
  assert.equal(replaced[0].complete, true);
  assert.equal(replaced[0].products.length, 2);
  assert.equal(createdTabs.length, 0);
  assert.equal(tabs.get(9).url, `${page}?site=2`);
  assert.equal(
    updates.some((item) => item.url === `${page}?site=2` && item.active === true),
    true,
  );
});

test("all-expansions crawler visits each set then stores URLs", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  const { worker, tabs, expansionImports, updates } = createHarness({
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
          ],
        };
      }
      if (String(href).includes("151")) {
        return {
          pageUrl: href,
          products: [{ url: `${first}/Bulbasaur-V1-MEW001`, name: "Bulbasaur" }],
          nextPage: null,
          expansions: [],
        };
      }
      return {
        pageUrl: href,
        products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
        nextPage: null,
        expansions: [],
      };
    },
  });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9" });
  const status = await worker.handleMessage({ type: "import-expansion-all" });
  const pages = productPages(expansionImports);
  assert.equal(pages.length, 2);
  assert.equal(pages[0].source, "crawl");
  assert.equal(pages[1].source, "crawl");
  assert.equal(pages[0].products[0].url.includes("Bulbasaur"), true);
  assert.equal(pages[1].products[0].url, GENGAR);
  assert.equal(
    updates.some((item) => item.url === first && item.active === true),
    true,
  );
  assert.equal(
    updates.some((item) => item.url === second && item.active === true),
    true,
  );
  assert.match(status.expansionNote, /All sets/);
});

test("all-expansions crawler skips sets already imported", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  const { worker, tabs, expansionImports } = createHarness({
    expansionCrawls: [{ complete: true, expansion: "151", expansion_id: "2770" }],
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
          ],
        };
      }
      if (String(href).includes("151")) {
        return {
          pageUrl: href,
          products: [{ url: `${first}/Bulbasaur-V1-MEW001`, name: "Bulbasaur" }],
          nextPage: null,
          expansions: [],
        };
      }
      return {
        pageUrl: href,
        products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
        nextPage: null,
        expansions: [],
      };
    },
  });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9" });
  const status = await worker.handleMessage({ type: "import-expansion-all" });
  const productImports = expansionImports.filter((item) => Array.isArray(item.products) && item.products.length);
  assert.equal(productImports.length, 1);
  assert.equal(productImports[0].products[0].url, GENGAR);
  assert.equal(
    expansionImports.some((item) => item.complete && item.expansion_id === "1234"),
    true,
  );
  assert.match(status.expansionNote, /All sets/);
});

test("Import all jumps to the first unfinished set", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  const third = "https://www.cardmarket.com/en/Pokemon/Products/Singles/World-Champions-Pack";
  const opened = [];
  const { worker, tabs, expansionImports } = createHarness({
    expansionCrawls: [
      { complete: true, expansion: "151", expansion_id: "2770" },
      { complete: true, expansion: "Tag Bolt", expansion_id: "1234" },
    ],
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      opened.push(href);
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
            { id: "9999", url: third, name: "World Champions Pack" },
          ],
        };
      }
      return {
        pageUrl: href,
        products: [{ url: `${href}/Pikachu-V4`, name: "Pikachu" }],
        nextPage: null,
        expansions: [],
      };
    },
  });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9" });
  const status = await worker.handleMessage({ type: "import-expansion-all" });
  const productImports = expansionImports.filter((item) => Array.isArray(item.products) && item.products.length);
  assert.equal(productImports.length, 1);
  assert.equal(productImports[0].products[0].url.includes("World-Champions-Pack"), true);
  assert.equal(opened.some((href) => href.includes("/151")), false);
  assert.equal(opened.some((href) => href.includes("Tag-Bolt")), false);
  assert.match(status.expansionNote, /All sets/);
});

test("Cloudflare pauses all-expansions and Continue resumes the same set", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  let blockTagBolt = true;
  const { worker, tabs, expansionImports, local } = createHarness({
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
          ],
        };
      }
      if (String(href).includes("151")) {
        return {
          pageUrl: href,
          products: [{ url: `${first}/Bulbasaur-V1-MEW001`, name: "Bulbasaur" }],
          nextPage: null,
          expansions: [],
        };
      }
      if (blockTagBolt) {
        return { pageUrl: href, products: [], nextPage: null, expansions: [], challenge: true };
      }
      return {
        pageUrl: href,
        products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
        nextPage: null,
        expansions: [],
      };
    },
  });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9" });
  const pausedStatus = await worker.handleMessage({ type: "import-expansion-all" });
  assert.equal(productPages(expansionImports).length, 1);
  assert.equal(expansionImports[0].products[0].url.includes("Bulbasaur"), true);
  assert.equal(pausedStatus.paused, true);
  assert.equal(pausedStatus.expansionResume.index, 1);
  assert.match(pausedStatus.expansionNote, /Continue/);
  assert.doesNotMatch(pausedStatus.expansionNote, /All sets/);

  blockTagBolt = false;
  const continued = await worker.handleMessage({ type: "resume" });
  const pages = productPages(expansionImports);
  assert.equal(pages.length, 2);
  assert.equal(pages[1].products[0].url, GENGAR);
  assert.equal(continued.paused, false);
  const stored = await local.get("expansionResume");
  assert.equal(stored.expansionResume, null);
  assert.match(continued.expansionNote, /All sets/);
});

test("Cloudflare tick auto-resumes without pressing Continue", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  let blockTagBolt = true;
  const { worker, tabs, expansionImports, local } = createHarness({
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
          ],
        };
      }
      if (String(href).includes("151")) {
        return {
          pageUrl: href,
          products: [{ url: `${first}/Bulbasaur-V1-MEW001`, name: "Bulbasaur" }],
          nextPage: null,
          expansions: [],
        };
      }
      if (blockTagBolt) {
        return { pageUrl: href, products: [], nextPage: null, expansions: [], challenge: true };
      }
      return {
        pageUrl: href,
        products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
        nextPage: null,
        expansions: [],
      };
    },
  });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9", title: "Singles" });
  await worker.handleMessage({ type: "import-expansion-all" });
  assert.equal(productPages(expansionImports).length, 1);
  blockTagBolt = false;
  const tab = { id: 9, url: second, active: true, documentId: "doc-9", title: "Tag Bolt", status: "complete" };
  tabs.set(9, tab);
  await worker.handleMessage({ type: "poll" });
  const pages = productPages(expansionImports);
  assert.equal(pages.length, 2);
  assert.equal(pages[1].products[0].url, GENGAR);
  const stored = await local.get(["paused", "expansionResume"]);
  assert.equal(stored.paused, false);
  assert.equal(stored.expansionResume, null);
});

test("manual Pause does not auto-resume when a set page finishes loading", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const { worker, tabs, local } = createHarness();
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9", title: "Singles", status: "complete" });
  await local.set({
    paused: true,
    expansionResume: { index: 2, targets: [{ id: "1", url: index, name: "151" }], reason: "paused" },
  });
  await worker.tabUpdated(
    9,
    { status: "complete" },
    { id: 9, url: index, title: "Singles", status: "complete" },
  );
  const stored = await local.get(["paused", "expansionResume"]);
  assert.equal(stored.paused, true);
  assert.equal(stored.expansionResume.reason, "paused");
});

test("sends an ntfy ping when Cloudflare pauses", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  const { worker, tabs, ntfyPosts, local } = createHarness({
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
          ],
        };
      }
      if (String(href).includes("151")) {
        return {
          pageUrl: href,
          products: [{ url: `${first}/Bulbasaur-V1-MEW001`, name: "Bulbasaur" }],
          nextPage: null,
          expansions: [],
        };
      }
      return { pageUrl: href, products: [], nextPage: null, expansions: [], challenge: true };
    },
  });
  await local.set({ ntfyTopic: "scanapp-cf-alerts-test" });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9" });
  await worker.handleMessage({ type: "import-expansion-all" });
  assert.equal(ntfyPosts.length, 1);
  assert.match(ntfyPosts[0].url, /ntfy\.sh\/scanapp-cf-alerts-test/);
  assert.match(String(ntfyPosts[0].body), /Cloudflare/);
});

test("Import all starts from the first set after a pause", async () => {
  const index = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151";
  const second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
  let blockTagBolt = true;
  const { worker, tabs, expansionImports } = createHarness({
    expansionExtract: (tab) => {
      const href = tab?.url || index;
      if (href === index || href.endsWith("/Singles")) {
        return {
          pageUrl: href,
          products: [],
          expansions: [
            { id: "2770", url: first, name: "151" },
            { id: "1234", url: second, name: "Tag Bolt" },
          ],
        };
      }
      if (String(href).includes("151")) {
        return {
          pageUrl: href,
          products: [{ url: `${first}/Bulbasaur-V1-MEW001`, name: "Bulbasaur" }],
          nextPage: null,
          expansions: [],
        };
      }
      if (blockTagBolt) {
        return { pageUrl: href, products: [], nextPage: null, expansions: [], challenge: true };
      }
      return {
        pageUrl: href,
        products: [{ url: GENGAR, name: "Gengar & Mimikyu GX" }],
        nextPage: null,
        expansions: [],
      };
    },
  });
  tabs.set(9, { id: 9, url: index, active: true, documentId: "doc-9" });
  await worker.handleMessage({ type: "import-expansion-all" });
  assert.equal(productPages(expansionImports).length, 1);
  blockTagBolt = false;
  const restarted = await worker.handleMessage({ type: "import-expansion-all" });
  const pages = productPages(expansionImports);
  assert.equal(pages.length, 2);
  assert.equal(pages[0].products[0].url.includes("Bulbasaur"), true);
  assert.equal(pages[1].products[0].url, GENGAR);
  assert.match(restarted.expansionNote, /All sets/);
});

test("startup unsticks a hung all-expansions crawl at the current set", async () => {
  const { worker, local } = createHarness();
  await local.set({
    expansionBusy: true,
    activity: "crawling-all-sets",
    lastExpansionImport: {
      expansionIndex: 130,
      stored: 5402,
      linked: 101,
      unmatched: 5301,
    },
    expansionNote: "Set 130/781: Cyber Judge · stored 5402",
  });
  await worker.wake("startup");
  const stored = await local.get(["expansionBusy", "paused", "expansionResume", "expansionNote"]);
  assert.equal(stored.expansionBusy, false);
  assert.equal(stored.paused, true);
  assert.equal(stored.expansionResume.index, 129);
  assert.match(stored.expansionNote, /Continue/);
});

test("keeps a helper token per Scanapp server", async () => {
  const { worker, local } = createHarness();
  await worker.handleMessage({
    type: "set-settings",
    apiBase: "http://127.0.0.1:8000",
    helperToken: "local-token",
  });
  await worker.handleMessage({
    type: "set-settings",
    apiBase: "https://staging-scan.auctaro.com",
    helperToken: "staging-token",
  });
  let stored = await local.get(["apiBase", "helperToken", "helperTokens"]);
  assert.equal(stored.apiBase, "https://staging-scan.auctaro.com");
  assert.equal(stored.helperToken, "staging-token");
  await worker.handleMessage({ type: "set-settings", apiBase: "http://127.0.0.1:8000" });
  stored = await local.get(["apiBase", "helperToken", "helperTokens"]);
  assert.equal(stored.apiBase, "http://127.0.0.1:8000");
  assert.equal(stored.helperToken, "local-token");
  assert.equal(stored.helperTokens["https://staging-scan.auctaro.com"], "staging-token");
});

test("saves crawl pace fast and between", async () => {
  const { worker, local } = createHarness();
  await worker.handleMessage({ type: "set-settings", expansionPace: "slow" });
  let stored = await local.get("expansionPace");
  assert.equal(stored.expansionPace, "between");
  await worker.handleMessage({ type: "set-settings", expansionPace: "medium" });
  stored = await local.get("expansionPace");
  assert.equal(stored.expansionPace, "between");
  await worker.handleMessage({ type: "set-settings", expansionPace: "between" });
  stored = await local.get("expansionPace");
  assert.equal(stored.expansionPace, "between");
  await worker.handleMessage({ type: "set-settings", expansionPace: "fast" });
  stored = await local.get("expansionPace");
  assert.equal(stored.expansionPace, "fast");
});

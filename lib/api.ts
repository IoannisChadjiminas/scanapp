import type {
  CardmarketPriceResponse,
  CardSummary,
  HealthResponse,
  PrepareResponse,
  ScanResponse,
  SessionResultsResponse,
} from "@/lib/api-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) {
      return payload.detail;
    }
  } catch {
    /* ignore */
  }
  if (response.status === 503) {
    return "The scanner is busy or not ready. Try again shortly.";
  }
  if (response.status === 413) {
    return "That photograph is too large.";
  }
  return `Request failed (${response.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as T;
}

export function assetUrl(path: string | null | undefined): string {
  if (!path) {
    return "";
  }
  if (path.startsWith("http")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<HealthResponse>("/api/v1/health", { signal }),
  prepare: async (file: File, signal?: AbortSignal) => {
    const body = new FormData();
    body.append("image", file);
    return request<PrepareResponse>("/api/v1/images/prepare", {
      method: "POST",
      body,
      signal,
    });
  },
  scan: async (
    blob: Blob,
    extras: Record<string, string>,
    signal?: AbortSignal,
  ) => {
    const body = new FormData();
    body.append("image", blob, "scan.jpg");
    for (const [key, value] of Object.entries(extras)) {
      body.append(key, value);
    }
    return request<ScanResponse>("/api/v1/scans", {
      method: "POST",
      body,
      signal,
    });
  },
  searchCards: (q: string, language?: string, signal?: AbortSignal) =>
    request<{ items: CardSummary[]; total: number }>(
      `/api/v1/cards?q=${encodeURIComponent(q)}${
        language && language !== "auto"
          ? `&language=${encodeURIComponent(language)}`
          : ""
      }`,
      { signal },
    ),
  feedback: (scanId: string, action: string, cardId?: string, cardmarketUrl?: string) =>
    request(`/api/v1/scans/${scanId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        card_id: cardId ?? null,
        cardmarket_url: cardmarketUrl ?? null,
      }),
    }),
  sessionResults: (signal?: AbortSignal) =>
    request<SessionResultsResponse>("/api/v1/session/results", { signal }),
  enqueueCardmarketJob: (url: string, cardId?: string) =>
    request<{ id: string; url: string; card_id: string }>("/api/v1/cardmarket/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, card_id: cardId ?? null }),
    }),
  cardmarketPrices: (url: string, signal?: AbortSignal) =>
    request<CardmarketPriceResponse>(
      `/api/v1/cardmarket/prices?url=${encodeURIComponent(url)}`,
      { signal },
    ),
  cardmarketPriceEventsUrl: (url: string) =>
    `${API_BASE}/api/v1/cardmarket/prices/events?url=${encodeURIComponent(url)}`,
};

export async function queueCardmarketLookup(url?: string | null, cardId?: string) {
  if (!url) {
    return;
  }
  try {
    await api.enqueueCardmarketJob(url, cardId);
  } catch {
    /* listing fetch must not block recognition */
  }
}

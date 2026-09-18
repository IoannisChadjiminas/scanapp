"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { CardmarketPrice, CardmarketPriceResponse } from "@/lib/api-types";

const GUIDE_LABELS = new Set(["From", "Trend", "7-day"]);

function formatAmount(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat("en-IE", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function isGuideOnly(prices: CardmarketPrice[] | undefined) {
  return Boolean(prices?.length) && prices!.every((item) => GUIDE_LABELS.has(item.label));
}

function formatObserved(iso: string | null | undefined) {
  if (!iso) {
    return null;
  }
  const ageMs = Date.now() - Date.parse(iso);
  if (!Number.isFinite(ageMs) || ageMs < 0) {
    return "Offers checked just now";
  }
  const mins = Math.round(ageMs / 60_000);
  if (mins < 1) {
    return "Offers checked just now";
  }
  if (mins === 1) {
    return "Offers checked 1 minute ago";
  }
  if (mins < 60) {
    return `Offers checked ${mins} minutes ago`;
  }
  const hours = Math.round(mins / 60);
  if (hours === 1) {
    return "Offers checked 1 hour ago";
  }
  return `Offers checked ${hours} hours ago`;
}

function statusMessage(
  payload: CardmarketPriceResponse,
  hasLive: boolean,
  waiting: boolean,
) {
  if (payload.helper_attention) {
    return "Cardmarket needs attention";
  }
  if (payload.helper_paused) {
    return "Helper paused";
  }
  if (hasLive) {
    return formatObserved(payload.observed_at) ?? "Cardmarket prices";
  }
  if (Array.isArray(payload.prices) && payload.prices.length) {
    return "Cardmarket guide prices";
  }
  if (payload.status === "done") {
    return "No listings on Cardmarket";
  }
  if (payload.helper_online === false) {
    return "Queued — helper offline";
  }
  if (payload.status === "failed" && !waiting) {
    return "Could not read Cardmarket listings";
  }
  if (
    payload.status === "pending" ||
    payload.status === "claimed" ||
    payload.status === "failed" ||
    waiting
  ) {
    return "Fetching offers";
  }
  return null;
}

function stillWaitingForOffers(payload: CardmarketPriceResponse, live: boolean) {
  if (live || payload.status === "done") {
    return false;
  }
  if (payload.helper_attention || payload.helper_paused || payload.helper_online === false) {
    return false;
  }
  return true;
}

export function CardmarketPrices({
  prices,
  waiting = false,
  message = null,
}: {
  prices?: CardmarketPrice[];
  waiting?: boolean;
  message?: string | null;
}) {
  if (!prices?.length && !waiting && !message) {
    return null;
  }
  const caption =
    message ||
    (waiting
      ? prices?.length
        ? "Guide prices — fetching live listings…"
        : "Fetching live Cardmarket listings…"
      : "Cardmarket prices");
  return (
    <div className="w-full">
      <p className="text-muted-foreground mb-2 text-xs">{caption}</p>
      {prices?.length ? (
        <div className="grid grid-cols-3 gap-2">
          {prices.map((item, index) => (
            <div
              key={`${item.label}-${item.amount}-${index}`}
              className="rounded-lg border px-2 py-2 text-center"
            >
              <p className="text-muted-foreground text-xs">{item.label}</p>
              <p className="font-medium tabular-nums">
                {formatAmount(item.amount, item.currency)}
              </p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function useCardmarketListings(
  url: string | null | undefined,
  initial: CardmarketPrice[] | undefined,
) {
  const [prices, setPrices] = useState(initial ?? []);
  const [waiting, setWaiting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setPrices(initial ?? []);
  }, [url, initial]);

  useEffect(() => {
    if (!url) {
      setWaiting(false);
      setMessage(null);
      return;
    }
    const needsLive = !initial?.length || isGuideOnly(initial);
    if (!needsLive) {
      setWaiting(false);
      setMessage(null);
      return;
    }
    let stopped = false;
    let attempts = 0;
    setWaiting(true);
    setMessage("Fetching offers");

    const tick = async () => {
      attempts += 1;
      try {
        const payload = await api.cardmarketPrices(url);
        if (stopped) {
          return;
        }
        const live = payload.prices.length > 0 && !isGuideOnly(payload.prices);
        if (payload.prices.length) {
          setPrices(payload.prices);
        }
        const keepGoing = stillWaitingForOffers(payload, live) && attempts < 45;
        setWaiting(keepGoing);
        setMessage(statusMessage(payload, live, keepGoing));
        if (!keepGoing) {
          return;
        }
      } catch {
        if (stopped) {
          return;
        }
        if (attempts < 45) {
          window.setTimeout(tick, 2000);
          return;
        }
        setWaiting(false);
        setMessage("Queued — helper offline");
        return;
      }
      if (stopped) {
        return;
      }
      window.setTimeout(tick, 2000);
    };
    void api
      .enqueueCardmarketJob(url)
      .catch(() => undefined)
      .then(() => {
        if (!stopped) {
          return tick();
        }
      });
    return () => {
      stopped = true;
    };
  }, [url]);

  return { prices, waiting, message };
}

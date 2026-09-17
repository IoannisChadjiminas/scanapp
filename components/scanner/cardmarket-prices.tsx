"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { CardmarketPrice } from "@/lib/api-types";

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

export function CardmarketPrices({
  prices,
  waiting = false,
}: {
  prices?: CardmarketPrice[];
  waiting?: boolean;
}) {
  if (!prices?.length && !waiting) {
    return null;
  }
  return (
    <div className="w-full">
      <p className="text-muted-foreground mb-2 text-xs">
        {waiting
          ? "Waiting for the PC helper to save Cardmarket listings…"
          : "Cardmarket prices"}
      </p>
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
  watching: boolean,
) {
  const [prices, setPrices] = useState(initial ?? []);
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    setPrices(initial ?? []);
  }, [url, initial]);

  useEffect(() => {
    if (!watching || !url) {
      setWaiting(false);
      return;
    }
    let stopped = false;
    let attempts = 0;
    setWaiting(true);

    const tick = async () => {
      attempts += 1;
      try {
        const payload = await api.cardmarketPrices(url);
        if (stopped) {
          return;
        }
        if (payload.prices.length) {
          setPrices(payload.prices);
          setWaiting(false);
          return;
        }
      } catch {
        /* helper may still be opening the page */
      }
      if (stopped) {
        return;
      }
      if (attempts >= 40) {
        setWaiting(false);
        return;
      }
      window.setTimeout(tick, 2000);
    };
    void tick();
    return () => {
      stopped = true;
    };
  }, [watching, url]);

  return { prices, waiting };
}

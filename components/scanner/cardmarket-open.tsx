"use client";

import { ExternalLink } from "lucide-react";
import { useState, type ReactNode } from "react";

import { api } from "@/lib/api";

type CardmarketOpenProps = {
  url: string;
  cardId?: string;
  className?: string;
  children?: ReactNode;
  showIcon?: boolean;
  onQueued?: () => void;
};

export function CardmarketOpen({
  url,
  cardId,
  className,
  children = "Open on Cardmarket",
  showIcon = true,
  onQueued,
}: CardmarketOpenProps) {
  const [busy, setBusy] = useState(false);

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-busy={busy}
      className={className}
      onClick={() => {
        onQueued?.();
        setBusy(true);
        void api.enqueueCardmarketJob(url, cardId).catch(() => {
          /* still open Cardmarket if the queue is down */
        });
      }}
    >
      {children}
      {showIcon ? <ExternalLink /> : null}
    </a>
  );
}

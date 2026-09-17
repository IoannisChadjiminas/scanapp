"use client";

import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ExternalLink } from "lucide-react";

import { useMediaQuery } from "@/hooks/use-media-query";
import { api, assetUrl } from "@/lib/api";
import type { CardSummary } from "@/lib/api-types";
import { languageLabel } from "@/lib/languages";

type CataloguePickerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (card: CardSummary) => void;
  language?: string;
};

function SearchBody({
  onSelect,
  language,
}: {
  onSelect: (card: CardSummary) => void;
  language?: string;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CardSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      api
        .searchCards(query, language, controller.signal)
        .then((payload) => {
          setItems(payload.items);
          setError(null);
        })
        .catch((cause: unknown) => {
          if (cause instanceof DOMException && cause.name === "AbortError") {
            return;
          }
          setError(cause instanceof Error ? cause.message : "Search failed");
        });
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [query, language]);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-2">
        <Label htmlFor="catalogue-search">Search the catalogue</Label>
        <Input
          id="catalogue-search"
          className="h-11"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name, set, or collector number"
          autoComplete="off"
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <ul className="grid max-h-[50vh] gap-2 overflow-y-auto">
        {items.map((card) => (
          <li key={card.id} className="flex items-stretch gap-2">
            <button
              type="button"
              className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-lg border px-3 py-2 text-left hover:bg-muted"
              onClick={() => onSelect(card)}
            >
              {card.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={assetUrl(card.image_url)}
                  alt=""
                  className="h-14 w-10 rounded object-cover"
                />
              ) : null}
              <span>
                <span className="block font-medium">{card.name}</span>
                <span className="block text-sm text-muted-foreground">
                  {card.set_name} · #{card.collector_number}
                  {card.language ? ` · ${languageLabel(card.language)}` : ""}
                </span>
              </span>
            </button>
            {card.cardmarket_url ? (
              <a
                href={card.cardmarket_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open ${card.name} on Cardmarket`}
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg border px-2 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <ExternalLink className="size-4" />
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CataloguePicker({
  open,
  onOpenChange,
  onSelect,
  language,
}: CataloguePickerProps) {
  const desktop = useMediaQuery("(min-width: 768px)");
  const title = "Correct the card";
  const description = "Search the indexed catalogue and pick the actual card.";

  if (desktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <SearchBody onSelect={onSelect} language={language} />
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[90vh] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          <SearchBody onSelect={onSelect} language={language} />
        </div>
      </SheetContent>
    </Sheet>
  );
}


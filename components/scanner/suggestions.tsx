"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "cn";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { assetUrl } from "@/lib/api";
import type { Candidate, CardmarketVariant, ScanStatus } from "@/lib/api-types";
import { languageLabel } from "@/lib/languages";
import { CardmarketOpen } from "@/components/scanner/cardmarket-open";
import {
  CardmarketPrices,
  useCardmarketListings,
} from "@/components/scanner/cardmarket-prices";

type SuggestionsProps = {
  status: ScanStatus;
  message: string | null;
  suggestions: Candidate[];
  onConfirm: (cardId: string, cardmarketUrl?: string | null) => void;
  onChooseAnother: () => void;
  onReject: () => void;
  onScanAgain: () => void;
};

function statusLabel(status: ScanStatus) {
  if (status === "matched") {
    return "Match";
  }
  if (status === "uncertain") {
    return "Uncertain";
  }
  if (status === "retake") {
    return "Retake";
  }
  if (status === "failed") {
    return "Failed";
  }
  return "Not a match";
}

function OfferBlock({
  url,
  prices,
}: {
  url?: string | null;
  prices?: Candidate["cardmarket_prices"];
}) {
  const listings = useCardmarketListings(url, prices);
  return (
    <CardmarketPrices
      prices={listings.prices}
      waiting={listings.waiting}
      message={listings.message}
    />
  );
}

function VariantPicker({
  variants,
  selected,
  onSelect,
}: {
  variants: CardmarketVariant[];
  selected: CardmarketVariant | null;
  onSelect: (variant: CardmarketVariant) => void;
}) {
  return (
    <div className="mt-3 flex flex-col gap-2">
      <p className="text-sm font-medium">Which Cardmarket listing is this?</p>
      {variants.map((variant) => {
        const active = selected?.url === variant.url;
        return (
          <button
            key={variant.url}
            type="button"
            onClick={() => onSelect(variant)}
            className={cn(
              "rounded-md border px-3 py-2 text-left text-sm",
              active ? "border-primary bg-primary/5" : "border-border",
            )}
          >
            <span className="font-medium">{variant.label || variant.slug}</span>
            {variant.slug ? (
              <span className="text-muted-foreground mt-0.5 block text-xs">
                {variant.slug}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function Suggestions({
  status,
  message,
  suggestions,
  onConfirm,
  onChooseAnother,
  onReject,
  onScanAgain,
}: SuggestionsProps) {
  const top = suggestions[0];
  const variants = top?.cardmarket_variants ?? [];
  const needsChoice = variants.length >= 2;
  const [selected, setSelected] = useState<CardmarketVariant | null>(null);
  const showCard = Boolean(top) && (status === "matched" || status === "uncertain");
  const notAMatch = status === "no_match";
  const listingUrl = needsChoice ? selected?.url : top?.cardmarket_url;
  const listingCardId = needsChoice
    ? selected?.card_id || top?.card_id
    : top?.card_id;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-medium">
          {showCard ? "Most likely card" : "Result"}
        </h2>
        <Badge variant={showCard ? "secondary" : "destructive"}>
          {statusLabel(status)}
        </Badge>
      </div>
      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

      {showCard && top ? (
        <Card>
          <CardHeader>
            <CardTitle>{top.name}</CardTitle>
            <CardDescription>
              {top.language ? `${languageLabel(top.language)} · ` : ""}
              {top.set_name} · #{top.collector_number}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={assetUrl(top.image_url)}
              alt={`${top.name} from ${top.set_name}`}
              className="mx-auto max-h-72 w-auto rounded-md"
            />
            {needsChoice ? (
              <VariantPicker
                variants={variants}
                selected={selected}
                onSelect={setSelected}
              />
            ) : null}
            <OfferBlock url={listingUrl} prices={needsChoice ? [] : top.cardmarket_prices} />
          </CardContent>
          <CardFooter className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-end">
            {listingUrl ? (
              <CardmarketOpen
                url={listingUrl}
                cardId={listingCardId}
                className={cn(
                  buttonVariants({ variant: "outline" }),
                  "h-11 min-h-11 w-full gap-2 sm:w-auto",
                )}
              />
            ) : (
              <p className="text-muted-foreground w-full text-sm">
                {needsChoice
                  ? "Choose a listing to open Cardmarket."
                  : "Cardmarket link unavailable."}
              </p>
            )}
            <Button
              type="button"
              variant="outline"
              className="h-11 min-h-11 w-full sm:w-auto"
              onClick={onReject}
            >
              Not this card
            </Button>
            <Button
              type="button"
              className="h-11 min-h-11 w-full sm:w-auto"
              disabled={needsChoice && !selected}
              onClick={() =>
                onConfirm(
                  selected?.card_id || top.card_id,
                  selected?.url ?? top.cardmarket_url,
                )
              }
            >
              This is the card
            </Button>
          </CardFooter>
        </Card>
      ) : null}

      {notAMatch ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyTitle>Not a match</EmptyTitle>
            <EmptyDescription>
              Nothing in the catalogue was close enough. Scan again with a tighter
              crop, or pick the card from the list.
            </EmptyDescription>
          </EmptyHeader>
          {top ? (
            <EmptyContent>
              <p className="text-muted-foreground text-xs">Closest card (not a match)</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={assetUrl(top.image_url)}
                alt=""
                className="mx-auto max-h-40 w-auto rounded-md opacity-70"
              />
              <p className="text-sm">
                {top.name} · {top.set_name} #{top.collector_number}
                {top.language ? ` · ${languageLabel(top.language)}` : ""}
              </p>
              <OfferBlock url={top.cardmarket_url} prices={top.cardmarket_prices} />
              {top.cardmarket_url ? (
                <CardmarketOpen
                  url={top.cardmarket_url}
                  cardId={top.card_id}
                  className="inline-flex items-center gap-1 text-sm underline-offset-4 hover:underline"
                />
              ) : null}
            </EmptyContent>
          ) : null}
        </Empty>
      ) : null}

      {status === "retake" || status === "failed" ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyTitle>{status === "retake" ? "Retake the photograph" : "Recognition failed"}</EmptyTitle>
            <EmptyDescription>
              {message ?? "Try a clearer, closer photograph of a single card."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        {notAMatch ? (
          <Button type="button" variant="secondary" className="h-11 min-h-11" onClick={onChooseAnother}>
            Choose from catalogue
          </Button>
        ) : (
          <Button type="button" variant="secondary" className="h-11 min-h-11" onClick={onChooseAnother}>
            Choose another
          </Button>
        )}
        <Button type="button" variant="outline" className="h-11 min-h-11" onClick={onScanAgain}>
          Scan again
        </Button>
      </div>
    </div>
  );
}

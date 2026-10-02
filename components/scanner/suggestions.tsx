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
import { api, assetUrl } from "@/lib/api";
import type { Candidate, CardSummary, CardmarketVariant, PrintingReview, ScanStatus } from "@/lib/api-types";
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
  printingReview: PrintingReview | null;
  onConfirm: (cardId: string, cardmarketUrl?: string | null, printingSelected?: boolean) => void;
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
  if (status === "printing_ambiguous") {
    return "Printing needs review";
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
              "flex items-center gap-3 rounded-md border px-3 py-2 text-left text-sm",
              active ? "border-primary bg-primary/5" : "border-border",
            )}
          >
            {variant.image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={assetUrl(variant.image)}
                alt=""
                className="h-20 w-auto rounded"
              />
            ) : null}
            <span>
              <span className="font-medium">{variant.label || variant.slug}</span>
              {variant.slug ? (
                <span className="text-muted-foreground mt-0.5 block text-xs">
                  {variant.slug}
                </span>
              ) : null}
            </span>
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
  printingReview,
  onConfirm,
  onChooseAnother,
  onReject,
  onScanAgain,
}: SuggestionsProps) {
  const top = suggestions[0];
  const [printing, setPrinting] = useState<CardSummary | null>(null);
  const [loadingPrinting, setLoadingPrinting] = useState(false);
  const [printingError, setPrintingError] = useState<string | null>(null);
  const ambiguous = status === "printing_ambiguous";
  const printingReady = !ambiguous || Boolean(printing);
  const displayed = printing ?? top;
  const cardId = printing?.id ?? top?.card_id;
  const variants = displayed?.cardmarket_variants ?? [];
  const needsChoice = variants.length >= 2;
  const [selected, setSelected] = useState<CardmarketVariant | null>(null);
  const showCard = Boolean(displayed) && (status === "matched" || status === "uncertain" || ambiguous);
  const notAMatch = status === "no_match";
  const listingUrl = printingReady ? (needsChoice ? selected?.url : displayed?.cardmarket_url) : null;
  const listingCardId = selected?.card_id || cardId;

  async function choosePrinting(id: string) {
    setLoadingPrinting(true);
    setPrintingError(null);
    setPrinting(null);
    setSelected(null);
    try {
      const detail = await api.card(id);
      if (detail.id !== id) throw new Error("Printing metadata did not match your choice.");
      setPrinting(detail);
    } catch (cause) {
      setPrintingError(cause instanceof Error ? cause.message : "Could not load that printing.");
    } finally {
      setLoadingPrinting(false);
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-medium">
          {ambiguous ? "Choose the printing" : showCard ? "Most likely card" : "Result"}
        </h2>
        <Badge variant={showCard ? "secondary" : "destructive"}>
          {statusLabel(status)}
        </Badge>
      </div>
      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

      {showCard && displayed ? (
        <Card>
          <CardHeader>
            <CardTitle>{displayed.name}</CardTitle>
            <CardDescription>
              {printingReady ? <>{displayed.language ? `${languageLabel(displayed.language)} · ` : ""}
                {displayed.set_name} · #{displayed.collector_number}</> : "The photograph does not prove a specific printing."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {displayed.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
              src={assetUrl(displayed.image_url)}
              alt={printingReady ? `${displayed.name} from ${displayed.set_name}` : `${displayed.name} reference — printing unconfirmed`}
              className="mx-auto max-h-72 w-auto rounded-md"
              />
            ) : null}
            {ambiguous ? (
              <div className="mt-3 flex flex-col gap-2">
                <p className="text-sm font-medium">Possible printings — compare your card</p>
                <p className="text-muted-foreground text-sm">{printingReview?.guidance ?? "Include all four corners and the collector number, or choose the printing manually."}</p>
                {printingReview?.plausible_printings.map((choice) => (
                  <button key={choice.card_id} type="button" disabled={loadingPrinting}
                    aria-pressed={printing?.id === choice.card_id}
                    onClick={() => void choosePrinting(choice.card_id)}
                    className={cn("rounded-md border px-3 py-2 text-left text-sm", printing?.id === choice.card_id ? "border-primary bg-primary/5" : "border-border")}>
                    {choice.set_name} · #{choice.collector_number} · {languageLabel(choice.language)}
                  </button>
                ))}
                {loadingPrinting ? <p role="status">Loading printing and finish choices…</p> : null}
                {printingError ? <p role="alert">{printingError}</p> : null}
              </div>
            ) : null}
            {printingReady && needsChoice ? (
              <VariantPicker
                variants={variants}
                selected={selected}
                onSelect={setSelected}
              />
            ) : null}
            {printingReady ? <OfferBlock url={listingUrl} prices={needsChoice || printing ? [] : top?.cardmarket_prices} /> : null}
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
                {!printingReady ? "Choose the printing before viewing prices or Cardmarket." : needsChoice
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
              disabled={!printingReady || loadingPrinting || (needsChoice && !selected)}
              onClick={() =>
                onConfirm(
                  (ambiguous ? printing?.id : selected?.card_id || cardId)!,
                  selected?.url ?? displayed.cardmarket_url,
                  ambiguous && Boolean(printing),
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

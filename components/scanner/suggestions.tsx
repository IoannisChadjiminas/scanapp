"use client";

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
import type { Candidate, ScanStatus } from "@/lib/api-types";
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
  onConfirm: (cardId: string) => void;
  onChooseAnother: () => void;
  onReject: () => void;
  onScanAgain: () => void;
};

function statusLabel(status: ScanStatus) {
  if (status === "matched") {
    return "Match";
  }
  if (status === "retake") {
    return "Retake";
  }
  if (status === "failed") {
    return "Failed";
  }
  return "Not a match";
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
  const matched = status === "matched" && top;
  const notAMatch = status === "no_match" || status === "uncertain";
  const listings = useCardmarketListings(
    top?.cardmarket_url,
    top?.cardmarket_prices,
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-medium">
          {matched ? "Most likely card" : "Result"}
        </h2>
        <Badge variant={matched ? "secondary" : "destructive"}>
          {statusLabel(status)}
        </Badge>
      </div>
      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

      {matched ? (
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
            <CardmarketPrices
              prices={listings.prices}
              waiting={listings.waiting}
              message={listings.message}
            />
          </CardContent>
          <CardFooter className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-end">
            {top.cardmarket_url ? (
              <CardmarketOpen
                url={top.cardmarket_url}
                cardId={top.card_id}
                className={cn(
                  buttonVariants({ variant: "outline" }),
                  "h-11 min-h-11 w-full gap-2 sm:w-auto",
                )}
              />
            ) : null}
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
              onClick={() => onConfirm(top.card_id)}
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
              <CardmarketPrices
                prices={listings.prices}
                waiting={listings.waiting}
                message={listings.message}
              />
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

"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { assetUrl } from "@/lib/api";
import type { Candidate, ScanStatus } from "@/lib/api-types";

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
    return "Matched";
  }
  if (status === "retake") {
    return "Retake";
  }
  if (status === "failed") {
    return "Failed";
  }
  return "Uncertain";
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
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-medium">Suggestions</h2>
        <Badge variant={status === "retake" ? "destructive" : "secondary"}>
          {statusLabel(status)}
        </Badge>
      </div>
      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
      <ol className="grid gap-3">
        {suggestions.map((item, index) => (
          <li key={item.card_id}>
            <Card>
              <CardHeader>
                <CardTitle>
                  {index + 1}. {item.name}
                </CardTitle>
                <CardDescription>
                  {item.set_name} · #{item.collector_number}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={assetUrl(item.image_url)}
                  alt={`${item.name} from ${item.set_name}`}
                  className="mx-auto max-h-64 w-auto rounded-md"
                />
              </CardContent>
              <CardFooter className="justify-end">
                <Button
                  type="button"
                  className="h-11 min-h-11"
                  onClick={() => onConfirm(item.card_id)}
                >
                  This is the card
                </Button>
              </CardFooter>
            </Card>
          </li>
        ))}
      </ol>
      <div className="grid gap-3 sm:grid-cols-3">
        <Button type="button" variant="secondary" className="h-11 min-h-11" onClick={onChooseAnother}>
          Choose another
        </Button>
        <Button type="button" variant="outline" className="h-11 min-h-11" onClick={onReject}>
          None of these
        </Button>
        <Button type="button" variant="outline" className="h-11 min-h-11" onClick={onScanAgain}>
          Scan again
        </Button>
      </div>
    </div>
  );
}

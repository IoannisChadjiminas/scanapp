"use client";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SessionResult } from "@/lib/api-types";

type SessionResultsProps = {
  results: SessionResult[];
  onExport: () => void;
};

function outcome(row: SessionResult) {
  if (row.rejected) {
    return "Rejected";
  }
  if (row.confirmed_card_id) {
    return row.confirmed_card_id;
  }
  if (row.status === "matched") {
    return "Match";
  }
  if (row.status === "no_match" || row.status === "uncertain") {
    return "Not a match";
  }
  return row.status;
}

export function SessionResults({ results, onExport }: SessionResultsProps) {
  if (results.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyTitle>No scans in this session</EmptyTitle>
          <EmptyDescription>
            Capture or upload a card to start recording anonymous results.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-medium">Session results</h2>
        <Button type="button" variant="outline" className="h-11 min-h-11" onClick={onExport}>
          Export CSV
        </Button>
      </div>
      <div className="md:hidden grid gap-3">
        {results.map((row) => (
          <div key={row.scan_id} className="rounded-xl border p-3 text-sm">
            <p className="font-medium">
              {row.suggestions[0]?.name ?? "No suggestion"}
            </p>
            <p className="text-muted-foreground">
              {new Date(row.created_at).toLocaleString()} · {outcome(row)}
            </p>
            <p className="text-muted-foreground">
              {row.timings_ms.total_ms ? `${Math.round(row.timings_ms.total_ms)} ms` : "—"}
            </p>
            {row.suggestions[0]?.cardmarket_url ? (
              <a
                href={row.suggestions[0].cardmarket_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm underline-offset-4 hover:underline"
              >
                Cardmarket
              </a>
            ) : null}
          </div>
        ))}
      </div>
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Top suggestion</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead>Latency</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((row) => (
              <TableRow key={row.scan_id}>
                <TableCell>{new Date(row.created_at).toLocaleString()}</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>
                  {row.suggestions[0]?.name ?? "—"}
                  {row.suggestions[0]?.cardmarket_url ? (
                    <>
                      {" "}
                      <a
                        href={row.suggestions[0].cardmarket_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline-offset-4 hover:underline"
                      >
                        Cardmarket
                      </a>
                    </>
                  ) : null}
                </TableCell>
                <TableCell>{outcome(row)}</TableCell>
                <TableCell>
                  {row.timings_ms.total_ms ? `${Math.round(row.timings_ms.total_ms)} ms` : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

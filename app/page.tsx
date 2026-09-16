import { ScannerApp } from "@/components/scanner/scanner-app";

export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col px-4 py-6">
      <header className="mb-6">
        <p className="text-sm font-medium text-muted-foreground">Scanapp experiment</p>
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Identify an English Pokémon card
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Photographs are processed, then discarded. Suggestions stay uncertain until
          development thresholds are frozen.
        </p>
      </header>
      <ScannerApp />
    </div>
  );
}

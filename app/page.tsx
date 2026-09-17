import { ScannerApp } from "@/components/scanner/scanner-app";

export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col px-4 py-6">
      <header className="mb-6">
        <p className="text-sm font-medium text-muted-foreground">Scanapp experiment</p>
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Identify a Pokémon card
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Take a photo. An English card should match the English print, a
          Japanese card the Japanese print, and so on — you do not pick the
          language first.
        </p>
      </header>
      <ScannerApp />
    </div>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CircleAlert, Upload } from "lucide-react";

import { CameraCapture } from "@/components/scanner/camera-capture";
import { CataloguePicker } from "@/components/scanner/catalogue-picker";
import { CropEditor } from "@/components/scanner/crop-editor";
import { SessionResults } from "@/components/scanner/session-results";
import { Suggestions } from "@/components/scanner/suggestions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, queueCardmarketLookup } from "@/lib/api";
import type { CardSummary, HealthResponse, ScanResponse, SessionResult } from "@/lib/api-types";
import { LANGUAGE_CHOICES, languageLabel } from "@/lib/languages";

type Stage = "idle" | "camera" | "crop" | "processing" | "result";

const LANGUAGE_STORAGE_KEY = "scanapp.cardLanguage";

function coverageText(health: HealthResponse) {
  const coverage = health.coverage;
  if (!coverage) {
    return null;
  }
  const languages = coverage.languages?.filter((item) => item.indexed > 0) ?? [];
  const languagePart = languages.length
    ? ` (${languages.map((item) => `${item.indexed} ${languageLabel(item.language)}`).join(", ")})`
    : "";
  const missing = coverage.missing_images
    ? ` · ${coverage.missing_images} missing reference images`
    : "";
  return `Indexed ${coverage.indexed} of ${coverage.cards} cards${languagePart}${missing}. Snapshot ${health.snapshot}.`;
}

function needsServerPreview(file: File) {
  const type = file.type.toLowerCase();
  return (
    type === "image/heic" ||
    type === "image/heif" ||
    type === "" ||
    (!type.startsWith("image/") && type !== "image/jpeg")
  );
}

export function ScannerApp() {
  const [stage, setStage] = useState<Stage>("idle");
  const [statusText, setStatusText] = useState("Ready to scan.");
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [results, setResults] = useState<SessionResult[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [tab, setTab] = useState("scan");
  const [language, setLanguage] = useState("auto");
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const revokePreview = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const refreshResults = useCallback(async () => {
    try {
      const payload = await api.sessionResults();
      setResults(payload.results);
    } catch {
      /* session results are best-effort until the first scan */
    }
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored) {
      setLanguage(stored);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then(setHealth)
      .catch(() =>
        setHealth({
          status: "unreachable",
          ready: false,
          catalogue_version: null,
          model_revision: null,
          preprocess_config: "unknown",
          use_ocr: true,
          snapshot: "missing",
          coverage: null,
          detail:
            "The recognition API is not running. Use Docker Compose at http://localhost:8080, or start the API on port 8000 and set NEXT_PUBLIC_API_BASE=http://localhost:8000.",
        }),
      );
    return () => controller.abort();
  }, []);

  useEffect(() => () => {
    abortRef.current?.abort();
    revokePreview();
  }, [revokePreview]);

  function resetToIdle() {
    abortRef.current?.abort();
    revokePreview();
    setPreviewUrl(null);
    setScan(null);
    setError(null);
    setStage("idle");
    setStatusText("Ready to scan.");
  }

  async function setPreviewFromBlob(blob: Blob) {
    revokePreview();
    const url = URL.createObjectURL(blob);
    objectUrlRef.current = url;
    setPreviewUrl(url);
    setStage("crop");
  }

  async function handleUpload(file: File) {
    setError(null);
    try {
      if (needsServerPreview(file)) {
        setStatusText("Preparing photograph for preview.");
        const prepared = await api.prepare(file);
        revokePreview();
        setPreviewUrl(`data:image/jpeg;base64,${prepared.image_base64}`);
        setStage("crop");
        return;
      }
      await setPreviewFromBlob(file);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not read that file.");
      setStage("idle");
    }
  }

  async function runScan(blob: Blob) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStage("processing");
    setStatusText("Identifying the card.");
    setError(null);
    try {
      const result = await api.scan(blob, { skip_detect: "true", language }, controller.signal);
      if (result.status === "matched" || result.status === "uncertain") {
        const top = result.suggestions[0];
        await queueCardmarketLookup(top?.cardmarket_url, top?.card_id);
      }
      setScan(result);
      setStage("result");
      setStatusText(
        result.status === "retake"
          ? result.message ?? "Please retake the photograph."
          : result.status === "matched"
            ? "Most likely card is ready."
            : result.status === "uncertain"
              ? "More than one print could match. Choose the correct card."
              : "Not a match.",
      );
      await refreshResults();
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        return;
      }
      setError(cause instanceof Error ? cause.message : "Recognition failed.");
      setStage("crop");
      setStatusText("Recognition failed.");
    }
  }

  async function sendFeedback(action: "confirm" | "correct" | "reject", cardId?: string) {
    if (!scan) {
      return;
    }
    try {
      await api.feedback(scan.id, action, cardId);
      if (action !== "reject") {
        const selected =
          scan.suggestions.find((item) => item.card_id === cardId) ?? scan.suggestions[0];
        await queueCardmarketLookup(selected?.cardmarket_url, cardId || selected?.card_id);
      }
      await refreshResults();
      setStatusText(
        action === "reject" ? "Suggestions rejected." : "Correction saved for this session.",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save feedback.");
    }
  }

  function exportCsv() {
    const header = ["scan_id", "created_at", "status", "top_suggestion", "confirmed_card_id", "rejected", "latency_ms"];
    const lines = results.map((row) =>
      [
        row.scan_id,
        row.created_at,
        row.status,
        row.suggestions[0]?.name ?? "",
        row.confirmed_card_id ?? "",
        String(row.rejected),
        row.timings_ms.total_ms ?? "",
      ]
        .map((value) => `"${String(value).replaceAll('"', '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "scanapp-session.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  function onCatalogueSelect(card: CardSummary) {
    setPickerOpen(false);
    queueCardmarketLookup(card.cardmarket_url, card.id);
    void sendFeedback("correct", card.id);
  }

  return (
    <div className="flex flex-col gap-6">
      {health && !health.ready ? (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>
            {health.status === "unreachable"
              ? "Recognition API is not running"
              : "Catalogue is not ready"}
          </AlertTitle>
          <AlertDescription>
            {health.detail ?? "Run the bootstrap container, then restart the API."}
          </AlertDescription>
        </Alert>
      ) : null}
      {health?.coverage ? (
        <p className="text-sm text-muted-foreground">{coverageText(health)}</p>
      ) : null}

      <div className="grid gap-2">
        <Label htmlFor="card-language">Language</Label>
        <select
          id="card-language"
          className="h-11 w-full rounded-lg border border-input bg-transparent px-2.5 text-base md:text-sm"
          value={language}
          onChange={(event) => {
            const next = event.target.value;
            setLanguage(next);
            window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next);
          }}
        >
          {LANGUAGE_CHOICES.map((code) => (
            <option key={code} value={code}>
              {languageLabel(code)}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          Leave Auto-detect on. The photograph chooses English, Japanese, or
          Chinese. Only lock a language if you want to search that catalogue
          alone.
        </p>
      </div>

      <div aria-live="polite" className="sr-only">
        {statusText}
      </div>

      <Tabs
        value={tab}
        onValueChange={(value) => {
          const next = String(value);
          setTab(next);
          if (next === "results") {
            void refreshResults();
          }
        }}
      >
        <TabsList className="w-full">
          <TabsTrigger value="scan" className="min-h-11">
            Scanner
          </TabsTrigger>
          <TabsTrigger value="results" className="min-h-11">
            Session
          </TabsTrigger>
        </TabsList>
        <TabsContent value="scan" className="pt-4">
          {error ? (
            <Alert variant="destructive" className="mb-4">
              <CircleAlert />
              <AlertTitle>Something went wrong</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {stage === "idle" ? (
            <div className="flex flex-col gap-3">
              <Button
                type="button"
                className="h-12 min-h-12 w-full"
                onClick={() => {
                  setError(null);
                  setStage("camera");
                }}
              >
                <Camera data-icon="inline-start" />
                Open camera
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-12 min-h-12 w-full"
                onClick={() => fileRef.current?.click()}
              >
                <Upload data-icon="inline-start" />
                Upload photograph
              </Button>
              <input
                id="photo-upload"
                ref={fileRef}
                className="sr-only"
                type="file"
                tabIndex={-1}
                aria-hidden="true"
                accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) {
                    void handleUpload(file);
                  }
                }}
              />
            </div>
          ) : null}

          {stage === "camera" ? (
            <CameraCapture
              onCapture={(blob) => void setPreviewFromBlob(blob)}
              onCancel={resetToIdle}
            />
          ) : null}

          {stage === "crop" && previewUrl ? (
            <CropEditor
              key={previewUrl}
              src={previewUrl}
              onConfirm={(blob) => void runScan(blob)}
              onRetry={resetToIdle}
            />
          ) : null}

          {stage === "processing" ? (
            <div className="flex flex-col gap-3" role="status">
              <p className="text-sm font-medium">Identifying the card…</p>
              <Skeleton className="h-72 w-full" />
              <Skeleton className="h-11 w-full" />
              <Button type="button" variant="outline" className="h-11 min-h-11" onClick={resetToIdle}>
                Cancel
              </Button>
            </div>
          ) : null}

          {stage === "result" && scan ? (
            <Suggestions
              status={scan.status}
              message={scan.message}
              suggestions={scan.suggestions}
              onConfirm={(cardId) => void sendFeedback("confirm", cardId)}
              onChooseAnother={() => setPickerOpen(true)}
              onReject={() => void sendFeedback("reject")}
              onScanAgain={resetToIdle}
            />
          ) : null}
        </TabsContent>
        <TabsContent value="results" className="pt-4">
          <SessionResults results={results} onExport={exportCsv} />
        </TabsContent>
      </Tabs>

      <CataloguePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={onCatalogueSelect}
        language={language}
      />
    </div>
  );
}

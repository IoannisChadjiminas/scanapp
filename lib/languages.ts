export const LANGUAGE_LABELS: Record<string, string> = {
  auto: "Auto-detect",
  en: "English",
  ja: "Japanese",
  zh: "Chinese",
  "zh-cn": "Chinese (Simplified)",
  "zh-tw": "Chinese (Traditional)",
  ko: "Korean",
  fr: "French",
  de: "German",
  es: "Spanish",
  it: "Italian",
  "pt-br": "Portuguese",
};

export const LANGUAGE_CHOICES = [
  "auto",
  "en",
  "ja",
  "zh-cn",
  "zh-tw",
  "ko",
] as const;

export function languageLabel(code: string | null | undefined) {
  if (!code) {
    return "";
  }
  return LANGUAGE_LABELS[code] ?? code;
}

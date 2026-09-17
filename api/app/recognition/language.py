from __future__ import annotations

from dataclasses import dataclass

LANGUAGE_GROUPS: dict[str, tuple[str, ...]] = {
    "en": ("en",),
    "ja": ("ja",),
    "jp": ("ja",),
    "zh": ("zh-cn", "zh-tw"),
    "zh-cn": ("zh-cn",),
    "zh-tw": ("zh-tw",),
    "cn": ("zh-cn",),
    "tw": ("zh-tw",),
    "ko": ("ko",),
    "kr": ("ko",),
    "fr": ("fr",),
    "de": ("de",),
    "es": ("es",),
    "it": ("it",),
    "pt": ("pt-br", "pt"),
    "pt-br": ("pt-br",),
    "id": ("id",),
    "th": ("th",),
}

LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "pt-br": "Portuguese (Brazil)",
    "id": "Indonesian",
    "th": "Thai",
}

TRADITIONAL_HINTS = set("龍劍氣與後過這個無東車門開見風雲點長語獸能量超進化")
SIMPLIFIED_HINTS = set("龙剑气与后过这个无东车门开见风云点长语兽能量超进化")

# Printed words that identify the card's language (stage, HP labels, etc.).
JA_PHRASES = ("たね", "1進化", "2進化", "ポケモン", "ワザ", "にげる", "抵抗力")
EN_PHRASES = (
    "basic pokemon",
    "basic pokémon",
    "evolves from",
    "retreat cost",
    "stage 1",
    "stage 2",
    "weakness",
    "resistance",
)
ZH_CN_PHRASES = ("宝可梦", "这个")
ZH_TW_PHRASES = ("寶可夢", "這個")
KO_PHRASES = ("포켓몬",)


@dataclass(frozen=True)
class LanguageDecision:
    requested: str
    detected: str | None
    search: tuple[str, ...]
    reason: str


def normalize_language_code(value: str | None) -> str:
    if not value:
        return "auto"
    return value.strip().lower().replace("_", "-")


def expand_language(code: str | None) -> tuple[str, ...]:
    normalized = normalize_language_code(code)
    if normalized in {"", "auto"}:
        return ()
    return LANGUAGE_GROUPS.get(normalized, (normalized,))


def language_label(code: str | None) -> str:
    if not code or code == "auto":
        return "Auto-detect"
    return LANGUAGE_LABELS.get(code, code)


def detect_card_language(texts: list[str]) -> str | None:
    blob = "\n".join(item for item in texts if item)
    if not blob:
        return None
    lowered = blob.casefold()
    hira = kata = hangul = cjk = latin = trad = simp = 0
    for char in blob:
        code = ord(char)
        if 0x3040 <= code <= 0x309F:
            hira += 1
        elif 0x30A0 <= code <= 0x30FF:
            kata += 1
        elif 0xAC00 <= code <= 0xD7A3:
            hangul += 1
        elif 0x4E00 <= code <= 0x9FFF:
            cjk += 1
            if char in TRADITIONAL_HINTS:
                trad += 1
            if char in SIMPLIFIED_HINTS:
                simp += 1
        elif char.isascii() and char.isalpha():
            latin += 1

    ja_words = sum(1 for phrase in JA_PHRASES if phrase in blob)
    en_words = sum(1 for phrase in EN_PHRASES if phrase in lowered)
    zh_cn_words = sum(1 for phrase in ZH_CN_PHRASES if phrase in blob)
    zh_tw_words = sum(1 for phrase in ZH_TW_PHRASES if phrase in blob)
    ko_words = sum(1 for phrase in KO_PHRASES if phrase in blob)

    if hira + kata >= 2 or ja_words:
        return "ja"
    if hangul >= 2 or ko_words:
        return "ko"
    if zh_tw_words > zh_cn_words:
        return "zh-tw"
    if zh_cn_words > zh_tw_words:
        return "zh-cn"
    if cjk >= 2:
        if trad > simp + 1:
            return "zh-tw"
        if simp > trad + 1:
            return "zh-cn"
        return "zh"
    if en_words or latin >= 8:
        return "en"
    return None


def detect_script_language(texts: list[str]) -> str | None:
    return detect_card_language(texts)


def resolve_search_languages(
    requested: str | None,
    texts: list[str],
) -> LanguageDecision:
    req = normalize_language_code(requested)
    detected = detect_card_language(texts)
    if req not in {"", "auto"}:
        return LanguageDecision(req, detected, expand_language(req), "user")
    # Auto searches every indexed print. Detected language only ranks English vs Japanese vs Chinese.
    return LanguageDecision("auto", detected, (), "ocr" if detected else "unknown")

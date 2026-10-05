# Recognition evidence and likely-card review

The scan response and session history now include an additive `confidence`
object. Legacy history rows without this evidence return `confidence: null`.
No results-database migration is required: evidence is persisted in `ocr_json`.

## Main match and alternatives for the app

Scan responses and session history now also expose these top-level attributes:

- `best_match`: the leading card object to show beside the user's photograph,
  with its name, catalogue ID, image URL, Cardmarket URL, scores and finish
  choices. This remains present for `uncertain` and `printing_ambiguous`
  responses; uncertainty no longer means there is no main card to display.
- `alternatives`: possible other cards/printings to show below the main result.
  The lead is excluded, same-printing aliases are deduplicated, and finish
  options stay on their card instead of becoming duplicate results. All offered
  printing choices are retained, plus at most five evidence-supported retrieval
  alternatives. An empty array means no additional plausible candidate was
  found, not that a finish was proved.
- `match_state`: `matched`, `likely`, `tentative`, or `unavailable`. Use this as
  a display badge, separately from printing/finish confirmation. These labels
  are not calibrated probabilities.

Example shape, abridged (the Umbreon case has a main match even though printing
confirmation is required):

```json
{
  "status": "printing_ambiguous",
  "match_state": "likely",
  "best_match": {
    "card_id": "en:swsh7-215",
    "name": "Umbreon VMAX",
    "collector_number": "215"
  },
  "alternatives": [],
  "confidence": {
    "requires_confirmation": true,
    "printing": "ambiguous",
    "finish": "unconfirmed"
  }
}
```

The layout is: user photo beside `best_match`, then `alternatives` below. Show
"Likely match" or "Tentative match" where appropriate instead of hiding the
card. Still use the existing printing picker when `printing_review` is present.
Do not interpret a main display card as a user-confirmed printing/finish.

Selection uses each option's `selection_action`. Offered printing choices use
`confirm` and still require `printing_selected: true` on printing-ambiguous
scans. A retrieved alternative outside that offered family uses `correct`, the
existing manual-correction path; it cannot bypass printing or URL/finish guards.
Unretrieved family members have null scores rather than fabricated zero scores.

`best_match` is null and `alternatives` empty for `retake`, `no_match` and
`failed`, or when neither ranking nor printing review has a candidate. The service does not invent
a match for a blank, unrelated, or unreadable input merely to populate a UI.
This change is additive presentation, not a change to retrieval, thresholds or
acceptance policy. Original `suggestions`, status and feedback rules are retained.
New display objects are persisted in `ocr_json.match_presentation`; history
replays those exactly and derives them for legacy scans from saved ranking.
If a legacy scan retained only printing-review choices, the first is an unscored
`tentative` main card, not a newly measured most-probable result. Load selected
card details for finish choices on unscored family members; an empty finish list
is not proof that only one finish exists.
History still distinguishes scan-time `best_match` from the user's later
`confirmed_card_id`. The presentation version is `best-match-v1`.

This updates the API contract locally. The Flutter layout and staging deployment
are not changed merely by adding these JSON fields.

Presentation validation (2026-10-02): **427 tests passed, one skipped**. A
network-disabled five-photo diagnostic (Umbreon twice, Charizard, Lugia and
Professor's Research) verifies that `best_match` equals the original leading
suggestion in every response, correct-printing returned recall remains 5/5,
and no recall regressions occur. Source hashes match the selected diagnostic
report: [recognition-best-match-smoke.json](recognition-best-match-smoke.json).
Tests also cover abstention nulls, full printing-family alternatives, nullable
scores outside retrieval, deduplication, history replay and feedback actions.
This is a presentation diagnostic, not a new full 69-photo accuracy run; the
previous full-sample reports are preserved unchanged.

Example from the previously rejected Umbreon VMAX photo (diagnostic run):

```json
{
  "status": "printing_ambiguous",
  "confidence": {
    "probability": null,
    "calibration_status": "uncalibrated",
    "candidate_card_id": "en:swsh7-215",
    "visual_similarity": 0.7706610560417175,
    "artwork_similarity": 0.709755003452301,
    "visual_margin": 0.10554540157318115,
    "name_ocr_confidence": 0.99416,
    "collector_ocr_confidence": null,
    "identity": "likely",
    "printing": "ambiguous",
    "finish": "unconfirmed",
    "requires_confirmation": true,
    "retake_recommended": false,
    "reasons": [
      "framing_unverified",
      "below_automatic_visual_threshold",
      "visual_streams_and_name_agree_review_only",
      "exact_printing_not_proven_by_name_and_number",
      "finish_not_inferred_from_static_photo"
    ]
  }
}
```

## Client interpretation

Similarity values are raw model similarities, not percentages of correctness.
OCR confidence is the OCR engine's score, not calibrated card identity
probability. A margin is lead minus runner-up **visual** similarity after
reranking; it can be negative when OCR or geometry changed order, or null when
there is no runner-up. No weighted composite is presented as a probability.

`probability` remains null until calibrated using a sufficiently large, labelled,
independent camera dataset containing wrong-card and unknown-card cases, not
only convenient catalogue positives. The current tuning/regression sample
cannot establish this calibration. Do not display `0.77` as "77% accuracy".

`candidate_card_id` identifies the candidate whose evidence is being reported,
including a hidden lead on a rejected scan. It is not a confirmation. Show
cards from `best_match` / `alternatives` (or the legacy `suggestions` /
`printing_review.plausible_printings`), never
surface a hidden rejected candidate merely because this ID is present.

`identity` is `unknown`, `conflicting`, `likely`, or `supported`. `printing` is
`unconfirmed`, `ambiguous`, or `metadata_supported`. Supported does not mean
infallible; metadata support is not proof of a finish. Finish stays unconfirmed
and confirmation remains a user action even for an ordinary `matched` result.
Confidence describes scan-time evidence; later user feedback does not turn it
into a new machine probability in session history.

## Less restrictive presentation without automatic overclaiming

The automatic visual threshold remains 0.78, the OCR-assisted floor 0.70 and
the existing gap 0.04. A lead below the automatic threshold may now be offered
for review if full-card and artwork retrieval both returned it, both visual
scores meet the OCR-assisted floor, and a meaningful name read at >=0.85 agrees.
These streams are corroborating retrieval signals, **not statistically
independent probabilities**. Known language and strong structured collector
contradictions still veto this rescue. Small/blurry images remain retakes.

Missing collector text means unknown printing, not failed card identity. Expand
the existing reference printing family when available; even one retrieved
printing can require review because absence of alternatives is not proof of
catalogue completeness. The existing `printing_ambiguous` status and explicit
`printing_selected` feedback guard enforce review. Cardmarket mappings and
finish selection are unchanged.

A small (<450px wide) frame with a strong name but no fraction/promo code may
receive one collector-region OCR retry, upscaled by at most 3x (target width
800px). Interpolation is not new visual evidence. Preserve first-pass hits and
their original scores; retain only explicit fractions or whole promo codes
from the optional retry only at OCR confidence >=0.85. Do not import incidental weakness/attack digits. A
retry failure preserves the first-pass result. The audit reports
`ocr.collector_retry_used`; it does not imply that a number was recovered.
`ocr.collector_retry_contributed` indicates that a structured retry observation
was retained. Such a read can support review, but cannot introduce an automatic
`matched` result. Weak retry fractions (including a diagnostic `200/1` read)
are ignored, while first-pass evidence remains unchanged.

The first exploratory retry admitted an incidental `2N` on Lugia and caused a
regression. That candidate was rejected and the accepted retry is restricted to
structured identifiers; the regression is covered by tests.

Policy revision: `rank-v7-likely-identity-review`. Implementation is local until
separately built/deployed and checked on staging. The opt-in artwork artifact
must be enabled for this dual-stream rescue; this change does not build or
deploy an artwork index, alter catalogue vectors, or write to PlanetScale.

## Regulation-mark OCR correction

The subsequent policy revision `rank-v8-regulation-mark-ocr` separates a single
modern regulation letter D–J from an immediately following **numeric fraction**
in OCR token extraction. For example, `D201/202` becomes collector evidence
`201/202`, preserving the OCR engine's original confidence and region. Raw OCR
hits remain unchanged in the audit. Generic catalogue-ID parsing is unchanged;
TG/GG/SM/SWSH/SVP prefixes, bare alphanumeric IDs and unknown multi-letter
namespaces are not stripped. Unknown-region/weak-confidence OCR stays unknown
or weak; different numerators and denominators still conflict.

On the diagnosed Professor's Research photo `trainer2_0`, the bottom regulation
mark merged into `D201/202` at confidence 0.95546. Both 201 and 209 previously
received a spurious prefix conflict, leaving the visual leader 209 first. The
corrected extraction makes **201 the primary `best_match`**, with `uncertain`
status and printing/finish confirmation still separate. A five-photo diagnostic
returns the correct best match for all five, with no returned-recall regressions:
[regulation smoke test](recognition-regulation-smoke.json).

**452 tests passed, one skipped**, including preservation of collector
namespaces/confidence, the 201-vs-209 ranking, selecting a genuinely observed
209 rather than hardcoding 201, metadata retrieval, printing review and
wrong-denominator rejection. A read-only audit of the current catalogue found
no single D–J prefixed numeric fractions in catalogue identifiers. This does
not certify future arbitrary namespaces or upgrade scores into probabilities.

This fix changes OCR evidence interpretation, not visual thresholds, models,
vectors, catalogue records or Cardmarket mappings. Local code only; no staging
deployment or Flutter rebuild is performed by this correction.

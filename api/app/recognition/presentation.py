"""Separate the card to display from certainty and printing/finish selection."""
from app.schemas import MatchOption, MatchPresentation, PrintingReview


def match_presentation(ranked: list[dict], *, status: str,
                       printing_review: PrintingReview | None,
                       min_visual: float = .70, max_retrieval_alternatives: int = 5) -> MatchPresentation:
    # A nearest neighbour of noise isn't a useful card match. Do not override
    # recognition, quality or confirmation policy merely to populate the UI.
    if status not in {'matched', 'uncertain', 'printing_ambiguous'}:
        return MatchPresentation()
    if not ranked:
        if not printing_review or not printing_review.plausible_printings:
            return MatchPresentation()
        # Some legacy scans retained review choices but no ranking. Offer the
        # first saved choice as tentative, without inventing a retrieval score.
        ranked = [{**printing_review.plausible_printings[0].model_dump(mode='json'),
                   'source':'printing_review'}]
    top = ranked[0]
    best = MatchOption.model_validate(top)
    state = 'matched' if status == 'matched' else 'likely'
    if top.get('visual_score') is None:
        state = 'tentative'
    if any(top.get(k) for k in ('strong_name_conflict', 'structured_collector_conflict',
                               'language_conflict', 'collector_conflict')):
        state = 'tentative'

    def key(row):
        return row['set_name'], row['collector_number'], row.get('language', '')

    seen = {key(top)}
    alternatives = []
    by_id = {r['card_id']: r for r in ranked}
    # Every offered printing is retained, including those outside vector top-K.
    # Unknown scores stay null. Finishes remain attached, not fake printings.
    if printing_review:
        for printing in printing_review.plausible_printings:
            row = printing.model_dump(mode='json')
            if key(row) in seen:
                continue
            seen.add(key(row))
            retrieved = by_id.get(printing.card_id, {})
            alternatives.append(MatchOption.model_validate({**retrieved, **row,
                                                           'source':'printing_review'}))
    added = 0
    for row in ranked[1:]:
        if key(row) in seen or any(row.get(k) for k in ('strong_name_conflict',
            'structured_collector_conflict', 'language_conflict')):
            continue
        if not (row.get('local_artwork_verified') or
                float(row.get('artwork_score') or 0) >= min_visual or
                (float(row['visual_score']) >= min_visual and
                 float(row['visual_score']) >= float(top['visual_score']) - .10)):
            continue
        if added >= max_retrieval_alternatives:
            break
        seen.add(key(row))
        alternatives.append(MatchOption.model_validate({**row,
            'selection_action':'correct' if status == 'printing_ambiguous' else 'confirm'}))
        added += 1
    return MatchPresentation(best_match=best, alternatives=alternatives, match_state=state)

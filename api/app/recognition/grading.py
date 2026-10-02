"""Conservative label OCR interpretation, isolated from card/printing ranking.

No grade is inferred from the card identity, numeric subgrades, a TAG score or
the company scale. Missing label evidence is NOT evidence of an ungraded card.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata

from app.schemas import GradingEvidence

VERSION = "slab-label-ocr-v3.4-contextual-fuzzy"
MIN_CONFIDENCE = .80

# Word boundaries deliberately reject Pokémon names, TAG TEAM and ACE SPEC.
BRANDS = {
    "psa": r"^(?:PSA|PSA\s+(?:GRADING|CARDS)|PROFESSIONAL SPORTS AUTHENTICATOR)$",
    "beckett": r"^(?:BECKETT(?: GRADING(?: SERVICES)?)?|BGS|BVG|BCCG)$",
    "cgc": r"^(?:CGC(?:\s*(?:CARDS|TRADING CARDS|GRADING|UNIVERSAL\s*GRADE))?|CERTIFIED GUARANTY COMPANY)$",
    "tag": r"^(?:TAG(?: GRADING)?|TECHNICAL AUTHENTICATION (?:AND|&) GRADING)$",
    "ace": r"^ACE(?: GRADING)?$",
    "ags": r"^(?:AGS(?: GRADING)?|AUTOMATED GRADING SYSTEMS|ROBOGRADING)$",
}
# Short acronyms are intentionally absent: an edit in PSA/CGC/TAG/ACE/AGS
# cannot be distinguished safely from incidental card text or another brand.
LONG_BRANDS = {
    "beckett": ("BECKETT", "BECKETT GRADING", "BECKETT GRADING SERVICES"),
    "psa": ("PROFESSIONAL SPORTS AUTHENTICATOR",),
    "cgc": ("CERTIFIED GUARANTY COMPANY",),
    "tag": ("TECHNICAL AUTHENTICATION AND GRADING",),
    "ags": ("AUTOMATED GRADING SYSTEMS", "ROBOGRADING"),
}
CONDITION = re.compile(
    r"^(?:GEM[ -]*(?:MINT|MT)|PRISTINE|PERFECT|MINT|MT|"
    r"NEAR[ -]*MINT(?:[ /-]*MINT)?\+?|MINT OR BETTER|MINT\+|NM[ /-]*(?:MT|MINT)\+?|NM\+?|EX(?:CELLENT)?[ -]*MT|"
    r"EX(?:CELLENT)?(?:[ /-]*(?:NM|MINT))?\+?|VERY GOOD(?:[ /-]*EX(?:CELLENT)?)?\+?|VG(?:[ /-]*EX)?\+?|"
    r"GOOD\+?|GD\+?|FAIR|FR|POOR|PR|AUTHENTIC(?:ATED)?(?:[ -]*ALTERED)?(?: AU| AA)?|AUTHENTIC ART ART)$"
)
NUMBER = r"(?:10(?:\.0)?|[1-9](?:\.[0-9])?)"
SUBGRADE = re.compile(r"\b(CENTERING|CENTRING|CORNERS?|EDGES?|SURFACES?)\b")


@dataclass(frozen=True)
class LabelLine:
    text: str
    confidence: float | None
    # Normalized label-strip rectangle. Location must be observed, not guessed.
    box: tuple[float, float, float, float] | None = None


def _text(value: str) -> str:
    value = value.replace('®','').replace('™','')
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).upper()).strip()


def brand_company(value: str) -> str | None:
    # Registered marks and a scales emblem are typography, not fuzzy OCR
    # guesses. Never accept PA/FSA/AG5 or card text such as TAG TEAM/ACE SPEC.
    text = _text(value.replace('®', '').replace('™', '')).strip()
    if text.startswith(('&CGC', '⚖CGC')):
        text = text.lstrip('&⚖').strip()
    return next((c for c,pattern in BRANDS.items() if re.fullmatch(pattern,text)),None)


def _condition(text: str, company: str | None) -> bool:
    # The native AGS label names remain native, never converted to a grade.
    return bool(CONDITION.fullmatch(text) or company == 'ags'
                and text in {'LEGENDARY','GEM MINT+','GEM-MT+'}
                or text == 'GEM.MINT')


def _condition_key(text: str) -> str:
    # Whitespace/punctuation variants observed on separate OCR passes are
    # not contradictory descriptors. Preserve the original display text.
    return re.sub(r'[ .-]', '', text)


def _within_one_edit(left: str, right: str) -> bool:
    """Bounded insertion/deletion/substitution; never correct numeric fields."""
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    if len(left) > len(right):
        left, right = right, left
    offset = 0
    for index, char in enumerate(left):
        if char != right[index + offset]:
            if offset or char != right[index + 1]:
                return False
            offset = 1
    return True


def fuzzy_company_candidates(lines: list[LabelLine]) -> set[str]:
    """Recover long issuer words only inside an independently located label.

    A descriptor, dated/numbered identity and one literal certificate must all
    be observed. This is never a general card-name, digit or acronym matcher.
    All text is retained for audit; a recovered issuer still needs confirmation.
    """
    located = [line for line in lines if line.box is not None
               and len(line.box) == 4 and all(math.isfinite(v) for v in line.box)
               and 0 <= line.box[0] < line.box[2] <= 1
               and 0 <= line.box[1] < line.box[3] <= 1
               and line.confidence is not None and math.isfinite(line.confidence)
               and line.confidence >= MIN_CONFIDENCE]
    identities = [line for line in located if _label_identity(_text(line.text))]
    conditions = [line for line in located if _condition(_text(line.text), None)
                  or (bool(m := re.fullmatch(rf'(.+?)\s+({NUMBER})', _text(line.text)))
                      and _condition(m[1], None))]
    certificates = [line for line in located if re.fullmatch(r'\d{6,14}', _text(line.text))]
    if (not identities or not conditions or not certificates
            or len({_text(line.text) for line in certificates}) != 1
            or not any(identity.box[1] < cert.box[1]
                       and _text(identity.text) != _text(cert.text)
                       for identity in identities for cert in certificates)):
        return set()
    top = min(line.box[1] for line in [*identities, *conditions]) - .15
    bottom = max(line.box[3] for line in [*certificates, *conditions]) + .10
    companies = set()
    for line in located:
        if line.confidence < .90 or not top <= line.box[1] <= bottom:
            continue
        text = _text(line.text).replace('&', 'AND').replace(' ', '')
        if len(text) < 6 or not text.isalpha() or brand_company(line.text):
            continue
        matches = {company for company, names in LONG_BRANDS.items()
                   if any(_within_one_edit(text, name.replace(' ', '')) for name in names)}
        if len(matches) == 1:
            companies.update(matches)
    return companies


def _label_identity(text: str) -> bool:
    return bool(re.search(r'\b(?:19|20)\d{2}\b',text) and re.search(r'\bPOK[ÉE]MON\b',text)
                # Dated set headers on ACE/BGS omit the Pokémon word. This
                # marker never suffices alone; a descriptor/cert or issuer is
                # still independently required by the caller.
                or re.match(r'^(?:19|20)\d{2}(?:[- /]\d{2})?\s*[A-Z][A-Z ]{3,}',text)
                # Set names can themselves be numeric. Require the complete
                # dated field, not an arbitrary number embedded in card text.
                or re.fullmatch(r'(?:19|20)\d{2}\s+\d{2,4}',text)
                or re.match(r'^#[A-Z]{0,4}\d{1,4}(?:[A-Z]{1,3})?(?:\s|$)',text))


def _valid_grade(value: str, company: str | None) -> float | None:
    number = float(value)
    if not 1 <= number <= 10:
        return None
    # AGS describes decimal precision; preserve it, not round to a half-point.
    if company != "ags" and number * 2 != round(number * 2):
        return None
    if company == "psa" and number == 9.5:
        return None
    return number


def has_label_context(lines: list[LabelLine]) -> bool:
    """Enough label structure to justify one targeted logo OCR retry."""
    texts = [_text(line.text) for line in lines if line.confidence is not None
             and math.isfinite(line.confidence) and line.confidence >= MIN_CONFIDENCE]
    company = next((brand_company(text) for text in texts if brand_company(text)),None)
    descriptor = any(_condition(text,company) or
                (bool(m := re.fullmatch(rf'(.+?)\s+({NUMBER})',text))
                 and _condition(m[1],company)) for text in texts)
    identities = {text for text in texts if _label_identity(text)}
    numeric_label = any(re.fullmatch(r'\d{6,14}',text)
                        and any(identity != text for identity in identities) for text in texts)
    # TAG's identifiers are alphanumeric and often vertical/QR encoded. A
    # located literal overall digit plus the descriptor and dated identity can
    # scope an official logo match; this does not decode a QR/cert number.
    located_grade = any(line.box is not None and re.fullmatch(NUMBER,_text(line.text))
                        and line.confidence is not None and math.isfinite(line.confidence)
                        and line.confidence >= MIN_CONFIDENCE for line in lines)
    return descriptor and (numeric_label or located_grade) and any(_label_identity(text) for text in texts)


def parse_label(lines: list[LabelLine], *, visual_company: str | None = None) -> GradingEvidence:
    reliable = [line for line in lines if line.confidence is not None
                and math.isfinite(line.confidence) and line.confidence >= MIN_CONFIDENCE]
    pairs = [(line, _text(line.text)) for line in reliable]
    # Initial label strips can also contain the photographed card's name/EX
    # suffix. A uniquely located certificate below dated label text bounds the
    # label; text well below it cannot contradict its condition descriptor.
    cert_lines = [line for line,text in pairs if re.fullmatch(r'\d{6,14}',text) and line.box]
    identities = [line for line,text in pairs if _label_identity(text) and line.box]
    # Repeated OCR of the same observed certificate must not remove the label
    # boundary and accidentally admit the photographed card's EX suffix.
    if cert_lines and len({_text(l.text) for l in cert_lines}) == 1 and all(
            abs((l.box[0]+l.box[2]-cert_lines[0].box[0]-cert_lines[0].box[2])/2)<.05
            and abs((l.box[1]+l.box[3]-cert_lines[0].box[1]-cert_lines[0].box[3])/2)<.05
            for l in cert_lines) and identities and any(
            line.box[1] < cert_lines[0].box[1] for line in identities):
        cert = cert_lines[0].box
        bottom = cert[3]+max(.025,1.5*(cert[3]-cert[1]))
        pairs = [(line,text) for line,text in pairs if line.box is None or line.box[1] <= bottom]
    companies = {company for _, text in pairs if (company := brand_company(text))}
    if visual_company in BRANDS and has_label_context(lines):
        companies.add(visual_company)
    else:
        visual_company = None
    if len(companies) > 1:
        return GradingEvidence(label_text=[line.text for line in lines],
            warnings=["conflicting_grading_companies", "include_one_card_and_its_complete_label"])
    company = next(iter(companies), None)
    conditions = []
    explicit_grades = []
    bare_grades = []
    subgrades: dict[str, set[float]] = {}
    separate_subgrades = []
    certificates = set()
    certificate_fields = []
    tag_scores = set()
    qualifiers = set()
    authenticated = False
    label_identity = False
    identity_texts = set()
    for line, text in pairs:
        if _label_identity(text):
            label_identity = True
            identity_texts.add(text)
        if re.fullmatch(r"(?:CERT(?:IFICATION)?(?: NO| NUMBER| #)?[: ]*)?\d{6,14}", text):
            certificates.add(re.search(r"\d{6,14}", text).group())
            certificate_fields.append(line)
        if company == 'tag' and re.fullmatch(r'[A-Z]\d{6,10}',text):
            certificates.add(text)
            certificate_fields.append(line)
        if company == "tag":
            score = re.fullmatch(r"(?:TAG )?SCORE[: ]+(\d{1,4})", text)
            if score and 1 <= int(score[1]) <= 1000:
                tag_scores.add(int(score[1]))
        for qualifier in re.findall(r"\((OC|ST|PD|MK|MC)\)", text):
            qualifiers.add(qualifier)
        if re.fullmatch(r"OC|ST|PD|MK|MC", text):
            qualifiers.add(text)
        # Read inline subgrades, never compute the overall grade from them.
        sub = SUBGRADE.search(text)
        if sub:
            values = re.findall(rf"(?<![\w./]){NUMBER}(?![\w./])", text[sub.end():])
            key = sub[1].lower().replace("centring", "centering").rstrip("s")
            key = {"corner": "corners", "edge": "edges"}.get(key, key)
            if len(values) == 1:
                value = _valid_grade(values[0], company)
                if value is not None:
                    subgrades.setdefault(key, set()).add(value)
            elif not values and line.box is not None:
                separate_subgrades.append((key, line))
            continue
        # Only an entire descriptor/grade line qualifies. Attack damage, HP,
        # dates, SKU/cert numbers and arbitrary promotional prose are excluded.
        descriptor = text
        grade_match = re.fullmatch(rf"(.+?)\s+({NUMBER})(?:\s+\((?:OC|ST|PD|MK|MC)\))?", text)
        if grade_match and _condition(grade_match[1],company):
            descriptor = grade_match[1]
            value = _valid_grade(grade_match[2], company)
            if value is not None:
                explicit_grades.append(value)
        elif (explicit := re.fullmatch(rf"(?:OVERALL )?GRADE[: ]+({NUMBER})", text)):
            value = _valid_grade(explicit[1], company)
            if value is not None:
                explicit_grades.append(value)
        elif re.fullmatch(NUMBER, text):
            value = _valid_grade(text, company)
            if value is not None:
                bare_grades.append((line, value))
        if _condition(descriptor,company):
            conditions.append((line, descriptor))
            authenticated |= descriptor.startswith("AUTHENTIC")

    # Company logos alone can be seller watermarks. The descriptor or a
    # dated/numbered grading label plus an explicit grade supplies context.
    context = bool(conditions or (label_identity and explicit_grades))
    # A tiny unreadable logo must not erase independently readable label data.
    # Without a supported issuer, demand stronger dated/numbered label context
    # AND a certification number. Keep company null, never infer it from colour.
    unbranded_context = bool(conditions and label_identity and certificates
                            and any(i != c for i in identity_texts for c in certificates))
    if not context or (not company and not unbranded_context):
        return GradingEvidence(label_text=[line.text for line in lines],
                              warnings=["no_supported_grading_label_detected",
                                        "ungraded_status_not_proven"])
    grade_values = set(explicit_grades)
    # Some labels print a subgrade above/below its heading rather than inline.
    # Require an unambiguous nearest aligned digit; never infer from all digits.
    for key, heading in separate_subgrades:
        hl, ht, hr, hb = heading.box
        aligned = []
        for number_line, value in bare_grades:
            if number_line.box is None:
                continue
            nl, nt, nr, nb = number_line.box
            gap = max(0., nt-hb, ht-nb)
            x_distance = abs((nl+nr-hl-hr)/2)
            if gap <= .12 and x_distance <= .10:
                aligned.append((gap+x_distance, value))
        aligned.sort()
        if aligned and (len(aligned) == 1 or aligned[1][0]-aligned[0][0] > .04):
            subgrades.setdefault(key,set()).add(aligned[0][1])
    # An isolated digit must be geometrically next to the condition descriptor.
    # Missing boxes cannot promote incidental numbers to an overall grade.
    if not authenticated:
        for number_line, value in bare_grades:
            if number_line.box is None:
                continue
            nl, nt, nr, nb = number_line.box
            for condition_line, _ in conditions:
                if condition_line.box is None:
                    continue
                cl, ct, cr, cb = condition_line.box
                vertical_gap = max(0., nt - cb, ct - nb)
                horizontal_gap = max(0., nl - cr, cl - nr)
                if vertical_gap <= .16 and horizontal_gap <= .22:
                    # Subgrades may be separate rows/columns next to their
                    # titles. Never mistake one of those digits for overall.
                    near_subgrade = any(other.box is not None and SUBGRADE.search(t)
                        and max(0., nt-other.box[3],other.box[1]-nb) <= .12
                        and abs((nl+nr-other.box[0]-other.box[2])/2) <= .10
                        for other, t in pairs)
                    if not near_subgrade:
                        grade_values.add(value)
    descriptor_groups = {_condition_key(text) for _,text in conditions}
    descriptors = {text for _, text in conditions}
    warnings = []
    if company is None:
        warnings.append("grading_company_unreadable_or_unsupported")
    if len(grade_values) > 1:
        warnings.append("conflicting_overall_grades")
    if authenticated and grade_values:
        warnings.append("authentication_label_has_numeric_grade_conflict")
    grade = next(iter(grade_values)) if len(grade_values) == 1 and not authenticated else None
    if grade is None and not authenticated:
        warnings.append("overall_grade_unreadable_or_ambiguous")
    if len(descriptor_groups) > 1:
        warnings.append("conflicting_condition_labels")
        grade = None
    # These top descriptors require 10 on the supported issuers' scales.
    # A contradictory observed digit must abstain; never infer/replace it with
    # 10. This also catches thresholding artifacts on gold embossed labels.
    if grade is not None and (
            descriptor_groups.intersection({'PRISTINE','PERFECT','LEGENDARY'}) and grade != 10
            or descriptor_groups.intersection({'GEMMINT','GEMMT','GEMMINT+'}) and grade < 9):
        grade = None
        warnings.append('condition_grade_contradiction')
    same_certificate_field = False
    if len(certificates)>1 and certificate_fields and all(l.box for l in certificate_fields):
        a=certificate_fields[0].box
        def same_field(line):
            b=line.box
            overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            area=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
            return area>0 and overlap>.60*area
        same_certificate_field=all(same_field(l) for l in certificate_fields)
    if len(certificates) > 1 and not same_certificate_field:
        # Multiple labels/copies may be in view. Never pick a copy's grade.
        grade = None
    if any(len(values) > 1 for values in subgrades.values()):
        warnings.append("conflicting_subgrades")
    if len(certificates) > 1:
        warnings.append("certification_number_unreadable_or_ambiguous" if same_certificate_field
                        else "certification_number_ambiguous")
    return GradingEvidence(slab_detected=True,
        is_graded=True if grade is not None else (False if authenticated else None),
        grading_status="graded" if grade is not None else ("authenticated_only" if authenticated else "unknown"),
        company=company, grade=grade,
        company_source='verified_logo' if visual_company == company and company is not None
            else ('label_ocr' if company is not None else 'none'),
        condition_label=next(iter(sorted(descriptors))) if len(descriptor_groups) == 1 else None,
        subgrades={key: next(iter(values)) for key, values in subgrades.items() if len(values) == 1},
        tag_score=next(iter(tag_scores)) if len(tag_scores) == 1 else None,
        certification_number=next(iter(certificates)) if len(certificates) == 1 else None,
        qualifiers=sorted(qualifiers), source="visible_label_ocr",
        label_text=[line.text for line in lines], warnings=warnings)


def recover_fuzzy_company(prior: GradingEvidence, views: list[list[LabelLine]]) -> GradingEvidence:
    """Company-only postprocessing: never change OCR flow or numeric outputs.

    Each supporting view must independently bind the same literal certificate
    and descriptor. A missing or conflicting grade cannot be repaired here.
    Existing literal/logo issuers are preserved, not downgraded to fuzzy ones.
    """
    conflicts = {'conflicting_grading_companies', 'conflicting_overall_grades',
                 'conflicting_condition_labels', 'certification_number_ambiguous',
                 'certification_number_unreadable_or_ambiguous',
                 'condition_grade_contradiction', 'authentication_label_has_numeric_grade_conflict',
                 'grading_ocr_failed'}
    if (prior.company is not None or prior.slab_detected is not True
            or not prior.certification_number or not prior.condition_label
            or conflicts.intersection(prior.warnings)):
        return prior
    candidates, supporting_text = set(), []
    for lines in views:
        guesses = fuzzy_company_candidates(lines)
        if not guesses:
            continue
        literal = parse_label(lines)
        if (conflicts.intersection(literal.warnings) - {'conflicting_overall_grades'}
                or literal.certification_number != prior.certification_number
                or literal.condition_label is None
                or _condition_key(literal.condition_label) != _condition_key(prior.condition_label)
                or literal.grade is not None and literal.grade != prior.grade):
            # A near-word from another holder/view must not fill this issuer.
            return prior
        if literal.company is not None:
            return prior
        if 'conflicting_overall_grades' in literal.warnings:
            # The established OCR path already selected a stronger literal
            # result. An unused retry's subgrade ambiguity cannot supply any
            # issuer or numeric evidence; keep searching consistent views.
            continue
        candidates.update(guesses)
        supporting_text.extend(line.text for line in lines)
    if len(candidates) != 1:
        return prior
    warnings = [warning for warning in prior.warnings
                if warning != 'grading_company_unreadable_or_unsupported']
    warnings.append('grading_company_fuzzy_match_requires_confirmation')
    return prior.model_copy(update={
        'company': next(iter(candidates)), 'company_source': 'label_ocr_fuzzy',
        'requires_confirmation': True, 'warnings': warnings,
        'label_text': list(dict.fromkeys([*prior.label_text, *supporting_text])),
    })

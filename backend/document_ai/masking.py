"""Step 7: mask identity and protected attributes before any text reaches a model.

Three layers, applied to every span:

1. The candidate's own known identity (name parts, email, phone) is replaced.
   This is exact and catches the name even when NER misses it.
2. Patterns catch emails, phones, links and street addresses.
3. Presidio NER (when PII_MASKER is "presidio") catches other people's names
   and, in contact sections, places.

Lines that state a protected attribute (date of birth, age, gender, marital
status, religion, caste, nationality, photo) are withheld from models entirely.
Gendered pronouns and titles are neutralized, so two resumes that differ only
in name or gender produce identical model input (see the counterfactual tests).
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from document_ai.vocabulary import TECH_TERMS

logger = logging.getLogger(__name__)

NAME = "[NAME]"
EMAIL = "[EMAIL]"
PHONE = "[PHONE]"
URL = "[URL]"
ADDRESS = "[ADDRESS]"
LOCATION = "[LOCATION]"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(
    r"(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab|twitter|x|facebook|instagram|behance|medium)\.com/\S*",
    re.IGNORECASE,
)
_PHONE = re.compile(
    r"(?<![\w-])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,5}\)[\s.-]?)?\d{3,5}[\s.-]?\d{3,5}(?:[\s.-]?\d{2,5})?(?![\w-])"
)
_ADDRESS = re.compile(
    r"\b\d{1,5}[,/ -]+(?:[A-Za-z0-9.'-]+\s){0,5}(?:street|st\.|road|rd\.?|avenue|ave\.?|lane|ln\.?|nagar|colony|"
    r"cross|main|sector|block|apartments?|flat)\b[^,\n]*",
    re.IGNORECASE,
)
_YEAR_RANGE = re.compile(r"(?:19|20)\d{2}\s*[-./]?\s*(?:(?:19|20)\d{2}|\d{2})")
_POSTCODE = re.compile(r"\b\d{3}\s?\d{3}\b|\b\d{5}(?:-\d{4})?\b")

_PROTECTED_LINE = re.compile(
    r"\b(date of birth|d\.?o\.?b\.?|birth ?date|born (on|in)|\d{2}\s*(years|yrs) old|gender|marital status|married|"
    r"unmarried|spouse|husband|wife|religion|caste|nationality|citizenship|blood group|father'?s name|"
    r"mother'?s name|passport (no|number))\b"
    r"|\b(age|sex|photo(graph)?)\s*[:\-]",
    re.IGNORECASE,
)

_PRONOUNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(he|she)\b", re.IGNORECASE), "they"),
    (re.compile(r"\b(him)\b", re.IGNORECASE), "them"),
    (re.compile(r"\b(his|her)\b", re.IGNORECASE), "their"),
    (re.compile(r"\b(hers)\b", re.IGNORECASE), "theirs"),
    (re.compile(r"\b(himself|herself)\b", re.IGNORECASE), "themself"),
    (re.compile(r"\b(mr|mrs|ms|miss|mx)\.?\s+", re.IGNORECASE), ""),
]

IDENTITY_SECTIONS = {"header", "contact", "personal"}


@dataclass(frozen=True, slots=True)
class Identity:
    full_name: str = ""
    email: str = ""
    phone: str = ""


@dataclass(frozen=True, slots=True)
class MaskResult:
    text: str
    withheld: bool
    replacements: int


def _keep_case(original: str, replacement: str) -> str:
    return replacement.capitalize() if original[:1].isupper() else replacement


def _neutralizer(neutral: str) -> "Callable[[re.Match[str]], str]":
    def replace(match: re.Match[str]) -> str:
        return _keep_case(match.group(0), neutral) if neutral else ""

    return replace


class Masker:
    def __init__(self, identity: Identity, *, use_presidio: bool, allow_terms: frozenset[str] = frozenset()) -> None:
        self.identity = identity
        self.use_presidio = use_presidio
        self.allow_terms = TECH_TERMS | {term.lower() for term in allow_terms}
        parts = [p for p in re.split(r"[\s.,]+", identity.full_name) if len(p) >= 3]
        names = sorted({identity.full_name.strip(), *parts}, key=len, reverse=True)
        self._name_patterns = [re.compile(rf"\b{re.escape(n)}\b", re.IGNORECASE) for n in names if n]

    def mask(self, text: str, section: str = "") -> MaskResult:
        if _PROTECTED_LINE.search(text):
            return MaskResult("", withheld=True, replacements=1)
        count = 0
        masked = text

        def sub(pattern: re.Pattern[str], token: str, value: str) -> str:
            nonlocal count
            result, n = pattern.subn(token, value)
            count += n
            return result

        if self.identity.email:
            masked = sub(re.compile(re.escape(self.identity.email), re.IGNORECASE), EMAIL, masked)
        masked = sub(_EMAIL, EMAIL, masked)
        masked = sub(_URL, URL, masked)
        for pattern in self._name_patterns:
            masked = sub(pattern, NAME, masked)
        masked, phones = _mask_phones(masked)
        count += phones
        masked = sub(_ADDRESS, ADDRESS, masked)
        if section in IDENTITY_SECTIONS:
            masked = sub(_POSTCODE, ADDRESS, masked)
        if self.use_presidio:
            masked, n = _presidio_mask(masked, section, self.allow_terms)
            count += n
        for pattern, neutral in _PRONOUNS:
            masked = pattern.sub(_neutralizer(neutral), masked)
        return MaskResult(" ".join(masked.split()), withheld=False, replacements=count)


def _mask_phones(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", match.group(0))
        # Years, date ranges and short numbers are not phones; a phone has at least 8 digits.
        if len(digits) < 8 or _YEAR_RANGE.fullmatch(match.group(0).strip()):
            return match.group(0)
        count += 1
        return PHONE

    return _PHONE.sub(replace, text), count


@lru_cache(maxsize=1)
def _presidio_engine() -> Any:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    provider = NlpEngineProvider(
        nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]}
    )
    return AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])


def _presidio_mask(text: str, section: str, allow_terms: frozenset[str]) -> tuple[str, int]:
    if not text.strip() or text.strip("[]").isupper():
        return text, 0
    entities = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "URL"]
    if section in IDENTITY_SECTIONS:
        entities.append("LOCATION")
    try:
        results = _presidio_engine().analyze(text=text, language="en", entities=entities, score_threshold=0.6)
    except Exception:
        logger.warning("presidio failed; pattern masking only", exc_info=True)
        return text, 0
    tokens = {"PERSON": NAME, "EMAIL_ADDRESS": EMAIL, "PHONE_NUMBER": PHONE, "URL": URL, "LOCATION": LOCATION}
    count = 0
    for result in sorted(results, key=lambda r: r.start, reverse=True):
        start, end = result.start, result.end
        if result.entity_type == "PERSON":
            bounds = person_bounds(text, start, end)
            if bounds is None:
                continue
            start, end = bounds
        value = text[start:end]
        words = {w.lower().strip(".,()") for w in value.split()}
        if value.startswith("[") or words & allow_terms:
            continue
        text = text[:start] + tokens[result.entity_type] + text[end:]
        count += 1
    return text, count


# A "name" ending in one of these is a company, which is not personal data.
_ORG_WORDS = frozenset(
    """labs lab systems technologies technology tech solutions software retail analytics networks logistics digital
    data media payments commerce health insurance energy mobility fintech pvt ltd limited inc llc llp corp corporation
    bank group services consulting university college institute""".split()
)


def person_bounds(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Narrow a PERSON detection to the name itself, or drop it when it is not a person.

    spaCy sometimes tags "Kestrel Labs 2025-Present" as a person. A name never contains
    digits, so the detection stops at the first word with one; that keeps dates readable
    for the parser. What is left is dropped if it ends in a company word.
    """
    words = list(re.finditer(r"\S+", text[start:end]))
    kept = []
    for word in words:
        if any(ch.isdigit() for ch in word.group()):
            break
        kept.append(word)
    if not kept:
        return None
    if kept[-1].group().lower().strip(".,()-") in _ORG_WORDS:
        return None
    return start + kept[0].start(), start + kept[-1].end()


def make_masker(identity: Identity, *, backend: str, allow_terms: frozenset[str] = frozenset()) -> Masker:
    return Masker(identity, use_presidio=backend == "presidio", allow_terms=allow_terms)

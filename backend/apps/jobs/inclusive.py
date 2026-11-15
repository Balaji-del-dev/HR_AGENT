"""Deterministic inclusive-language and protected-attribute checks for JDs and messages.

The Compliance Assistant reports these flags; it does not block. People decide.
"""

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class LanguageFlag:
    term: str
    category: str
    suggestion: str
    start: int
    end: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


# (pattern, category, suggestion)
_RULES: list[tuple[str, str, str]] = [
    (r"\b(rock ?star|ninja|guru|wizard|jedi)s?\b", "exclusionary_jargon", "Name the skill instead, e.g. 'expert'."),
    (r"\b(young|youthful|energetic young|digital natives?)\b", "age", "Describe the work, not the person's age."),
    (r"\b(recent (college )?graduates? only|fresh graduates? only)\b", "age", "Describe the experience level needed."),
    (r"\b(under|below) (the age of )?\d{2}\b", "age", "Remove age limits unless the law requires them."),
    (r"\b\d{2}\s*-\s*\d{2} years? old\b", "age", "Remove age ranges."),
    (r"\b(he|him|his|she|her|hers)\b", "gendered_pronoun", "Use 'they' or 'you'."),
    (
        r"\b(manpower|chairman|salesman|salesmen|foreman|craftsman)\b",
        "gendered_term",
        "Use a neutral term such as 'staff', 'chair' or 'salesperson'.",
    ),
    (r"\b(native (english )?speakers?)\b", "national_origin", "Say 'fluent in English'."),
    (
        r"\b(able[- ]bodied|physically fit)\b",
        "disability",
        "List the actual physical requirements, if any, and offer accommodations.",
    ),
    (r"\bculture fit\b", "vague_bias_risk", "Name the values or behaviours you mean."),
    (r"\b(aggressive|dominant|competitive spirit)\b", "gender_coded", "Use 'ambitious', 'driven' or 'proactive'."),
    (
        r"\b(married|unmarried|single|bachelor) (candidates?|applicants?)\b",
        "marital_status",
        "Remove marital status requirements.",
    ),
    (
        r"\b(christian|hindu|muslim|sikh|jewish) (candidates?|applicants?)\b",
        "religion",
        "Remove religious requirements.",
    ),
    (r"\b(caste|community certificate)\b", "caste", "Remove caste references."),
]
_COMPILED = [(re.compile(pattern, re.IGNORECASE), category, suggestion) for pattern, category, suggestion in _RULES]


def check_inclusive_language(text: str) -> list[LanguageFlag]:
    flags: list[LanguageFlag] = []
    for regex, category, suggestion in _COMPILED:
        for match in regex.finditer(text or ""):
            flags.append(LanguageFlag(match.group(0), category, suggestion, match.start(), match.end()))
    return sorted(flags, key=lambda flag: flag.start)

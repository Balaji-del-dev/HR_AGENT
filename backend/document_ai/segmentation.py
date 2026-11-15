"""Step 6: split pages into sections and lines, each with a stable span id.

A span id names the document, page and character offsets within that page's
text: ``doc_8f2a1b3c:p2:1840-1912``. The Validation Agent later checks every
cited quote against exactly this text.
"""

import re
from dataclasses import dataclass

SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "profile", "professional summary", "about me", "objective", "career objective"),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "employment",
        "work history",
        "career history",
    ),
    "education": ("education", "academic background", "qualifications", "academics"),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "technologies",
        "tech stack",
        "core competencies",
    ),
    "certifications": ("certifications", "certificates", "licenses", "licences", "certifications and licenses"),
    "projects": ("projects", "key projects", "personal projects"),
    "personal": ("personal details", "personal information", "personal data"),
    "contact": ("contact", "contact details", "contact information"),
}
_HEADING_LOOKUP = {alias: section for section, aliases in SECTION_HEADINGS.items() for alias in aliases}

CHUNK_MAX_CHARS = 700


@dataclass(frozen=True, slots=True)
class Span:
    span_id: str
    page: int
    start: int
    end: int
    section: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    section: str
    span_ids: tuple[str, ...]


def make_span_id(document_short_id: str, page: int, start: int, end: int) -> str:
    return f"doc_{document_short_id}:p{page}:{start}-{end}"


_SPAN_ID = re.compile(r"^doc_(?P<doc>[0-9a-f]{8}):p(?P<page>\d+):(?P<start>\d+)-(?P<end>\d+)$")


def parse_span_id(span_id: str) -> tuple[str, int, int, int] | None:
    match = _SPAN_ID.match(span_id or "")
    if not match:
        return None
    return match["doc"], int(match["page"]), int(match["start"]), int(match["end"])


def heading_section(line: str) -> str | None:
    candidate = line.strip().strip(":").strip().lower()
    candidate = re.sub(r"[^a-z &]", "", candidate).strip()
    if not candidate or len(candidate) > 40:
        return None
    return _HEADING_LOOKUP.get(candidate)


def segment(document_short_id: str, pages: list[str]) -> list[Span]:
    spans: list[Span] = []
    section = "header"
    for page_index, text in enumerate(pages, start=1):
        offset = 0
        for raw_line in text.split("\n"):
            start = offset
            offset += len(raw_line) + 1
            line = raw_line.strip()
            if not line:
                continue
            heading = heading_section(line)
            if heading:
                section = heading
            lead = len(raw_line) - len(raw_line.lstrip())
            span_start = start + lead
            span_end = span_start + len(line)
            spans.append(
                Span(
                    span_id=make_span_id(document_short_id, page_index, span_start, span_end),
                    page=page_index,
                    start=span_start,
                    end=span_end,
                    section="heading" if heading else section,
                    text=line,
                )
            )
    return spans


def chunk(spans: list[Span], masked: dict[str, str]) -> list[Chunk]:
    """Group consecutive spans of one section into chunks of masked text."""
    chunks: list[Chunk] = []
    current: list[str] = []
    current_section = ""
    size = 0
    for span in spans:
        text = masked.get(span.span_id, "")
        if not text or span.section == "heading":
            continue
        if current and (span.section != current_section or size + len(text) > CHUNK_MAX_CHARS):
            chunks.append(Chunk(current_section, tuple(current)))
            current, size = [], 0
        current_section = span.section
        current.append(span.span_id)
        size += len(text) + 1
    if current:
        chunks.append(Chunk(current_section, tuple(current)))
    return chunks

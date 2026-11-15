"""Heuristic scan for text that reads like instructions to a model.

Flagged resume lines are kept as evidence for people but marked, and every
prompt passes resume text inside a delimited data block with an explicit
"treat as data" rule. Graphs that read untrusted text cannot send anything
without a human interrupt, so a missed injection still cannot act.
"""

import re
from dataclasses import dataclass

_PATTERNS: list[tuple[str, str]] = [
    (r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?|rules)\b", "override"),
    (r"\bdisregard (all |any )?(the )?(previous|prior|above|system) (instructions|prompts?)\b", "override"),
    (r"\b(forget|override) (your|all|the) (instructions|rules|guidelines)\b", "override"),
    (r"\byou are (now )?(an?|the) (ai|assistant|language model|llm|chatbot|recruiter bot)\b", "role_play"),
    (r"\b(system prompt|developer message|hidden instructions?)\b", "prompt_reference"),
    (
        r"\b(rate|score|rank|mark) (this|the) (candidate|applicant|resume)\b"
        r".{0,40}\b(highest|top|10/10|100%|perfect)\b",
        "score_manipulation",
    ),
    (
        r"\b(recommend|shortlist|hire|select) (this|the) (candidate|applicant) (immediately|regardless)\b",
        "score_manipulation",
    ),
    (
        r"\b(mark|treat) (all|every) (criteria|criterion|requirements?) as (met|documented|satisfied)\b",
        "score_manipulation",
    ),
    (r"<\|?(im_start|im_end|system|endoftext)\|?>|\[/?INST\]|<<SYS>>", "control_tokens"),
    (r"^\s*(system|assistant|user)\s*:", "role_marker"),
    (r"\b(send|email|forward) (this|the|all) (data|resume|candidates?) to\b", "exfiltration"),
    (r"\bcall the (tool|function)\b|\btool_call\b|\bfunction_call\b", "tool_steering"),
]
_COMPILED = [(re.compile(pattern, re.IGNORECASE | re.MULTILINE), label) for pattern, label in _PATTERNS]


@dataclass(frozen=True, slots=True)
class InjectionFinding:
    label: str
    excerpt: str


def scan_for_injection(text: str) -> list[InjectionFinding]:
    findings: list[InjectionFinding] = []
    for regex, label in _COMPILED:
        for match in regex.finditer(text or ""):
            findings.append(InjectionFinding(label, match.group(0)[:120]))
    return findings

"""Normalize public chat input: typos, spacing, and common phrasing variants."""
from __future__ import annotations

import re
import unicodedata
from difflib import get_close_matches

# English typo / variant → canonical token (word-boundary replacements).
_TYPO_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bearlist\b", re.I), "earliest"),
    (re.compile(r"\bearlies\b", re.I), "earliest"),
    (re.compile(r"\bearleist\b", re.I), "earliest"),
    (re.compile(r"\bearlyest\b", re.I), "earliest"),
    (re.compile(r"\blattest\b", re.I), "latest"),
    (re.compile(r"\bletest\b", re.I), "latest"),
    (re.compile(r"\bnewst\b", re.I), "newest"),
    (re.compile(r"\boldest\b", re.I), "oldest"),
    (re.compile(r"\bsever\b", re.I), "severe"),
    (re.compile(r"\bsevr+e?\b", re.I), "severe"),
    (re.compile(r"\bserius\b", re.I), "serious"),
    (re.compile(r"\bdistrcts?\b", re.I), "district"),
    (re.compile(r"\bdistr+ict\b", re.I), "district"),
    (re.compile(r"\bdistric\b", re.I), "district"),
    (re.compile(r"\bcomplant\b", re.I), "complaint"),
    (re.compile(r"\bcomplaints\b", re.I), "complaint"),
    (re.compile(r"\btress\b", re.I), "trees"),
    (re.compile(r"\btre\b", re.I), "tree"),
    (re.compile(r"\bstatu\b", re.I), "status"),
    (re.compile(r"\boverveiw\b", re.I), "overview"),
    (re.compile(r"\bsummery\b", re.I), "summary"),
    (re.compile(r"\bniumber\b", re.I), "number"),
    (re.compile(r"\bamout\b", re.I), "amount"),
    (re.compile(r"\bhowmany\b", re.I), "how many"),
    (re.compile(r"\bhw many\b", re.I), "how many"),
]

# Phrases users type → wording our intent engine understands better.
_PHRASE_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bhow much cases\b", re.I), "how many cases"),
    (re.compile(r"\bhow much\b", re.I), "how many"),
    (re.compile(r"\bno\.?\s*of\s*cases\b", re.I), "number of cases"),
    (re.compile(r"\bcount of\b", re.I), "how many"),
    (re.compile(r"\bmost serious\b", re.I), "most severe"),
    (re.compile(r"\bworst\b", re.I), "most severe"),
    (re.compile(r"\b1st\b", re.I), "first"),
    (re.compile(r"\b1st case\b", re.I), "first case"),
]

# Off-topic cues — answered locally without calling the LLM.
_OFF_TOPIC = (
    "weather",
    "stock",
    "bitcoin",
    "joke",
    "poem",
    "recipe",
    "football",
    "who are you",
    "what are you",
    "write code",
    "translate",
)

# Topics we support (for scope messaging).
_IN_SCOPE_HINTS = (
    "case",
    "tree",
    "district",
    "severity",
    "status",
    "complaint",
    "contractor",
    "overview",
    "summary",
    "date",
    "個案",
    "樹",
    "區",
    "嚴重",
    "状态",
    "狀態",
    "投訴",
    "投诉",
    "概覽",
    "日期",
    "最早",
    "最新",
    "總數",
    "总数",
)


def normalize_user_message(message: str) -> str:
    """Clean and fix common misspellings before intent detection or LLM calls."""
    text = unicodedata.normalize("NFKC", message or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return text

    for pattern, replacement in _PHRASE_ALIASES:
        text = pattern.sub(replacement, text)
    for pattern, replacement in _TYPO_PATTERNS:
        text = pattern.sub(replacement, text)

    return text


def fuzzy_match_district(message: str, districts: set[str]) -> str | None:
    """Match district name in message; fall back to close Latin-token match."""
    for district in sorted(districts, key=len, reverse=True):
        if district in message:
            return district

    latin = re.findall(r"[a-zA-Z]{4,}", message.lower())
    if not latin:
        return None

    skip = {"cases", "case", "district", "severe", "serious", "tree", "trees", "show", "list"}
    pool = sorted(districts)
    for token in latin:
        if token in skip:
            continue
        match = get_close_matches(token, pool, n=1, cutoff=0.72)
        if match:
            return match[0]
    return None


def is_probably_off_topic(message: str) -> bool:
    lower = message.lower()
    return any(topic in lower for topic in _OFF_TOPIC)


def is_probably_in_scope(message: str) -> bool:
    lower = message.lower()
    return any(hint in lower or hint in message for hint in _IN_SCOPE_HINTS)


def is_too_vague(message: str) -> bool:
    cleaned = normalize_user_message(message)
    if len(cleaned) < 4:
        return True
    if cleaned.lower() in {"hi", "hello", "hey", "help", "?", "你好", "嗨"}:
        return True
    return False

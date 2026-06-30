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
    (re.compile(r"\bbrifing\b", re.I), "briefing"),
    (re.compile(r"\bniumber\b", re.I), "number"),
    (re.compile(r"\bamout\b", re.I), "amount"),
    (re.compile(r"\badjust\s+the\s+report\b", re.I), "show"),
    (re.compile(r"\bonly\s+(20\d{2})\b", re.I), r"only \1 cases"),
    (re.compile(r"\bhw many\b", re.I), "how many"),
    (re.compile(r"\bmore\s+that\b", re.I), "more than"),
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
    """Whether the message looks like a tree-complaint data question."""
    return is_dataset_data_question(message)


_GENERAL_DATE_RE = re.compile(
    r"\b("
    r"today'?s?\s+date|what\s+is\s+today'?s?\s+date|what\s+date\s+is\s+it|"
    r"what\s+day\s+is\s+it|current\s+date|今天(是)?几?号|今日日期|幾號|几号"
    r")\b",
    re.I,
)


def is_dataset_data_question(message: str) -> bool:
    """Question needs tree-complaint rows / summary (not general knowledge)."""
    cleaned = normalize_user_message(message)
    if not cleaned:
        return False
    lower = cleaned.lower()
    if _GENERAL_DATE_RE.search(lower):
        return False
    if is_system_meta_question(message):
        return False
    dataset_cues = (
        "case",
        "tree",
        "district",
        "severity",
        "status",
        "complaint",
        "contractor",
        "overview",
        "case_date",
        "case_no",
        "個案",
        "樹",
        "區",
        "嚴重",
        "状态",
        "狀態",
        "投訴",
        "投诉",
        "概覽",
        "最早",
        "最新",
        "總數",
        "总数",
        "earliest",
        "latest",
        "top ",
        "rank",
        "how many",
        "narrative",
        "briefing",
    )
    if any(c in lower or c in cleaned for c in dataset_cues):
        return True
    if re.search(r"\b(20\d{2})\b", cleaned) and re.search(
        r"\b(case|cases|month|year|date|月|年)\b", lower
    ):
        return True
    return False


def is_open_general_question(message: str) -> bool:
    """General knowledge / chit-chat — answer with AI (or local shortcuts), not dataset rules."""
    if is_dataset_data_question(message) or is_system_meta_question(message):
        return False
    cleaned = normalize_user_message(message)
    if not cleaned or is_too_vague(cleaned):
        return False
    return True


def is_too_vague(message: str) -> bool:
    cleaned = normalize_user_message(message)
    if len(cleaned) < 4:
        return True
    if cleaned.lower() in {"hi", "hello", "hey", "help", "?", "你好", "嗨"}:
        return True
    return False


_EXPORT_PHRASES: tuple[str, ...] = (
    "download report",
    "download chat",
    "download html",
    "export report",
    "export chat",
    "export html",
    "save report",
    "save chat",
    "get report",
    "下載報告",
    "下载报告",
    "導出報告",
    "导出报告",
    "下載聊天",
    "导出聊天",
)


def is_export_request(message: str) -> bool:
    """User wants to download an HTML report of their chat session."""
    cleaned = normalize_user_message(message).lower().strip()
    if not cleaned or len(cleaned) > 100:
        return False
    return any(phrase in cleaned for phrase in _EXPORT_PHRASES)


_META_MODEL_RE = re.compile(
    r"\b("
    r"ollama|deepseek|llm|"
    r"what\s+model|which\s+model|what\s+is\s+the\s+model|"
    r"model\s+name|model\s+running|model\s+used|"
    r"model\s+configured|currently\s+running|running\s+model|"
    r"model\s+last\s+(updated|modified)|last\s+updated|"
    r"when\s+was\s+.*\bmodel\b|date\s+of\s+the\s+model|"
    r"what\s+ai|which\s+ai|ai\s+model|"
    r"who\s+(built|made)\s+(this|the)\s+(bot|chatbot|assistant|analyst)"
    r")\b",
    re.I,
)

_DATA_CONTEXT_RE = re.compile(
    r"\b(case|cases|tree|trees|complaint|district|case_date|case_no|個案|樹|投訴|投诉)\b",
    re.I,
)


def is_system_meta_question(message: str) -> bool:
    """Questions about this chatbot / LLM setup — not tree-complaint data."""
    cleaned = normalize_user_message(message)
    if not cleaned:
        return False
    if not _META_MODEL_RE.search(cleaned):
        return False
    # e.g. "model" in a data-science sense with case/tree context — keep in data path.
    if _DATA_CONTEXT_RE.search(cleaned):
        return False
    return True

"""Build collapsible prompt / reasoning traces for the chat UI."""
from __future__ import annotations

import html
import json
from typing import Any


def build_prompt_trace_html(title: str, sections: list[tuple[str, str]]) -> str:
    """Render a <details> block with labelled preformatted sections."""
    parts: list[str] = []
    for heading, body in sections:
        if not body:
            continue
        parts.append(
            '<div class="prompt-trace-section">'
            f"<h4>{html.escape(heading)}</h4>"
            f"<pre>{html.escape(body)}</pre>"
            "</div>"
        )
    if not parts:
        return ""
    return (
        '<details class="prompt-trace">'
        f"<summary>{html.escape(title)}</summary>"
        + "".join(parts)
        + "</details>"
    )


def build_ai_prompt_trace(
    messages: list[dict[str, str]],
    *,
    model: str,
    source: str = "ai",
) -> str:
    """Show the full message list sent to the LLM."""
    route = {
        "ai": f"Answered by LLM ({model})",
        "timeout": f"LLM timed out ({model}) — prompt shown for debugging",
        "error": f"LLM error ({model}) — prompt shown for debugging",
    }.get(source, f"LLM path ({model})")

    sections: list[tuple[str, str]] = [("Routing", route), ("Model", model)]
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if i == 0 and role == "system":
            label = "System prompt"
        elif i == len(messages) - 1 and role == "user":
            label = "User prompt sent to model"
        else:
            label = f"Context message ({role})"
        sections.append((label, content))
    return build_prompt_trace_html("View prompt & how the AI was asked", sections)


def build_local_prompt_trace(trace: dict[str, Any]) -> str:
    """Explain how a local (non-LLM) answer was produced."""
    sections: list[tuple[str, str]] = []

    if trace.get("route_label"):
        sections.append(("Routing", str(trace["route_label"])))
    if trace.get("handler"):
        sections.append(("Handler", str(trace["handler"])))
    if trace.get("normalized_question"):
        orig = trace.get("original_question")
        if orig and orig != trace["normalized_question"]:
            sections.append(("Original question", str(orig)))
        sections.append(("Normalized question", str(trace["normalized_question"])))
    if trace.get("intent"):
        sections.append(("Detected intent", str(trace["intent"])))
    if trace.get("filters"):
        sections.append(
            (
                "Filters applied",
                json.dumps(trace["filters"], ensure_ascii=False, indent=2),
            )
        )
    if trace.get("logic"):
        sections.append(("Logic", str(trace["logic"])))
    if trace.get("data_preview"):
        sections.append(("Data used", str(trace["data_preview"])))
    if trace.get("note"):
        sections.append(("Note", str(trace["note"])))

    title = trace.get("title") or "View local reasoning & rules"
    return build_prompt_trace_html(title, sections)

"""The structured result of a run: the JSON schema the agent must answer with, and a summary."""

from __future__ import annotations

from typing import Any

_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "providers", "files_written", "test_run", "consumer_bugs",
                 "skipped_calls", "notes"],  # fmt: skip
    "properties": {
        "status": {
            "type": "string",
            "enum": ["passed", "failed", "blocked"],
            "description": "passed: the contract tests ran green. failed: they ran and some fail "
            "(e.g. a consumer bug not fixed). blocked: they couldn't be written or run.",
        },
        "summary": {**_STR, "description": "Two or three sentences for a pull request description."},
        "providers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["base_url_property", "spec_repo", "spec_path", "spec_version",
                             "why_this_version", "calls"],  # fmt: skip
                "properties": {
                    "base_url_property": _STR,
                    "spec_repo": _STR,
                    "spec_path": _STR,
                    "spec_version": _STR,
                    "why_this_version": _STR,
                    "calls": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["call", "example_files", "test"],
                            "properties": {"call": _STR, "example_files": _STRS, "test": _STR},
                        },
                    },
                },
            },
        },
        "files_written": _STRS,
        "test_run": {
            "type": "object",
            "additionalProperties": False,
            "required": ["command", "passed", "failed", "output_excerpt"],
            "properties": {
                "command": _STR,
                "passed": {"type": "integer"},
                "failed": {"type": "integer"},
                "output_excerpt": {**_STR, "description": "The failure lines, if any; else ''"},
            },
        },
        "consumer_bugs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["description", "evidence", "location", "fixed"],
                "properties": {"description": _STR, "evidence": _STR, "location": _STR,
                               "fixed": {"type": "boolean"}},  # fmt: skip
            },
        },
        "skipped_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["call", "reason"],
                "properties": {"call": _STR, "reason": _STR},
            },
        },
        "notes": _STRS,
    },
}


def render(report: dict[str, Any], cost_usd: float | None, turns: int | None) -> str:
    """The report as short Markdown, for a terminal or a PR comment."""
    run = report.get("test_run") or {}
    lines = [f"## Contract tests: {report.get('status', '?')}", "", report.get("summary", ""), ""]
    for p in report.get("providers") or []:
        lines.append(f"**{p['spec_repo']}/{p['spec_path']}** (v{p['spec_version']}, "
                     f"`{p['base_url_property']}`): {p['why_this_version']}")  # fmt: skip
        lines += [f"- {c['call']} → {c['test']}" for c in p["calls"]]
    lines += ["", f"Tests: {run.get('passed', 0)} passed, {run.get('failed', 0)} failed (`{run.get('command', '')}`)"]
    for bug in report.get("consumer_bugs") or []:
        lines.append(f"- **Consumer bug** ({'fixed' if bug['fixed'] else 'not fixed'}) in "
                     f"{bug['location']}: {bug['description']}")  # fmt: skip
    for skipped in report.get("skipped_calls") or []:
        lines.append(f"- Skipped {skipped['call']}: {skipped['reason']}")
    if report.get("files_written"):
        lines += ["", "Files: " + ", ".join(f"`{f}`" for f in report["files_written"])]
    lines += [f"- {n}" for n in report.get("notes") or []]
    if cost_usd is not None or turns is not None:
        lines += ["", f"_{turns or 0} turns, ${cost_usd or 0:.2f}_"]
    return "\n".join(lines).strip() + "\n"

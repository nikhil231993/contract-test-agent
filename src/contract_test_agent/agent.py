"""Run the agent: the Claude Agent SDK with test-context-graph, the spec finder, the guard hook,
limits and a structured report."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .config import AgentConfig
from .guard import pre_tool_use_hook
from .prompts import SYSTEM_PROMPT, task_prompt
from .report import REPORT_SCHEMA

# Built-in tools the agent gets; guard.py decides each call. Everything else (web, subagents)
# is left out of its context.
BUILT_IN_TOOLS = ["Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Bash", "TodoWrite"]
NOT_AVAILABLE = ["WebFetch", "WebSearch", "Task", "NotebookEdit"]


@dataclass
class RunResult:
    report: dict[str, Any] | None  # the structured report; None when the run ended in an error
    subtype: str  # "success", or why it stopped: error_max_turns, error_max_budget_usd...
    cost_usd: float | None = None
    turns: int | None = None
    errors: list[str] = field(default_factory=list)
    denials: int = 0  # tool calls the guard refused

    @property
    def ok(self) -> bool:
        return self.report is not None and self.report.get("status") == "passed"


def mcp_servers(config: AgentConfig) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {
        "tcg": {"type": "stdio", "command": config.tcg_mcp, "args": ["--index", str(config.index_dir)]},
        "specs": {"type": "stdio", "command": config.ghes_mcp},
    }
    if config.artifactory_mcp:
        servers["mocks"] = {"type": "stdio", "command": config.artifactory_mcp}
    return servers


def build_options(config: AgentConfig) -> ClaudeAgentOptions:
    async def guard(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        return await pre_tool_use_hook(config, dict(hook_input))

    servers = mcp_servers(config)
    return ClaudeAgentOptions(
        model=config.model,
        effort=config.effort,
        system_prompt={"type": "preset", "preset": "claude_code", "append": SYSTEM_PROMPT},
        cwd=str(config.consumer),
        add_dirs=[str(config.work_dir)],
        mcp_servers=servers,
        strict_mcp_config=True,  # only these servers, not the user's own
        setting_sources=[],  # no user or project settings: the same run everywhere
        # dontAsk: anything not pre-approved is denied, never prompted. The guard hook runs
        # before every call and denies what the rules in guard.py don't allow.
        permission_mode="dontAsk",
        allowed_tools=[*BUILT_IN_TOOLS, *(f"mcp__{name}" for name in servers)],
        disallowed_tools=NOT_AVAILABLE,
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guard])]},
        max_turns=config.max_turns,
        max_budget_usd=config.budget_usd,
        output_format={"type": "json_schema", "schema": REPORT_SCHEMA},
    )


def describe(block: ToolUseBlock) -> str:
    """One line per tool call, for the progress log."""
    data = block.input or {}
    detail = data.get("command") or data.get("file_path") or data.get("path") or data.get("pattern")
    if detail is None and block.name.startswith("mcp__"):
        detail = data.get("call") or data.get("api_url") or data.get("symbol") or ""
    return f"{block.name} {detail or ''}".strip()


async def run(config: AgentConfig, log: Callable[[str], None] = print) -> RunResult:
    config.work_dir.mkdir(parents=True, exist_ok=True)
    config.specs_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(report=None, subtype="no_result")
    async for message in query(prompt=task_prompt(config), options=build_options(config)):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    log(f"→ {describe(block)}")
                elif isinstance(block, TextBlock) and block.text.strip():
                    log(block.text.strip())
        elif isinstance(message, ResultMessage):
            result = RunResult(
                report=message.structured_output if message.subtype == "success" else None,
                subtype=message.subtype,
                cost_usd=message.total_cost_usd,
                turns=message.num_turns,
                errors=list(message.errors or []),
                denials=len(message.permission_denials or []),
            )
    return result

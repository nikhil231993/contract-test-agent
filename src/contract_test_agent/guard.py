"""What the agent may do: every tool call goes through decide() first (a PreToolUse hook).

The rules, so a run is safe to leave alone in CI:
- Reads stay in the consumer repo and the work dir (no ~/.ssh, no other repos).
- Writes go to the consumer's tests, its Specmatic files and its build file (to add the test
  dependency), or to the work dir. Its main code only with allow_fixes; otherwise the agent
  reports a consumer bug instead of fixing it.
- Shell commands: one plain command (no pipes, chains, redirects or substitutions) from a short
  list: tcg index, mvn, java -jar <the Specmatic jar>, read-only git.
- MCP tools of the configured servers are allowed; anything else is denied.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .config import AgentConfig

_FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
_READ_TOOLS = {"Read": "file_path", "Glob": "path", "Grep": "path"}
_SHELL_SYNTAX = set(";&|`$<>\n")  # chains, pipes, substitutions, redirects: one plain command only
_BUILD_FILES = {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
_SPECMATIC_FILES = {"specmatic.yaml", "specmatic.yml", "specmatic.json"}
_GIT_READ_ONLY = {"status", "diff", "log", "show"}
MCP_SERVERS = ("tcg", "specs", "mocks")  # the names agent.py registers the servers under


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


ALLOW = Decision(True)


def deny(reason: str) -> Decision:
    return Decision(False, reason)


def decide(tool: str, tool_input: dict[str, Any], config: AgentConfig) -> Decision:
    if tool in _FILE_TOOLS:
        return _write(tool_input.get(_FILE_TOOLS[tool]), config)
    if tool in _READ_TOOLS:
        return _read(tool_input.get(_READ_TOOLS[tool]), config)
    if tool == "Bash":
        return _bash(str(tool_input.get("command", "")), config)
    if tool.startswith("mcp__"):
        server = tool.split("__")[1] if tool.count("__") >= 2 else ""
        return ALLOW if server in MCP_SERVERS else deny(f"MCP server {server!r} is not configured")
    if tool in ("TodoWrite", "ToolSearch"):
        return ALLOW
    return deny(f"{tool} is not available to this agent")


def _resolve(path: str | None, config: AgentConfig) -> Path | None:
    if not path:
        return None
    p = Path(path).expanduser()
    return (p if p.is_absolute() else config.consumer / p).resolve()


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _read(path: str | None, config: AgentConfig) -> Decision:
    target = _resolve(path, config)
    if target is None:  # Glob/Grep without a path: the working directory, the consumer
        return ALLOW
    if _inside(target, config.consumer) or _inside(target, config.work_dir):
        return ALLOW
    return deny(f"reading outside the consumer repo and the work dir is not allowed: {target}")


def _write(path: str | None, config: AgentConfig) -> Decision:
    target = _resolve(path, config)
    if target is None:
        return deny("no file path given")
    if _inside(target, config.work_dir):
        return ALLOW
    if not _inside(target, config.consumer):
        return deny(f"writing outside the consumer repo and the work dir is not allowed: {target}")
    parts = PurePosixPath(target.relative_to(config.consumer).as_posix()).parts
    if not parts or parts[0] == ".git" or ".github" in parts:
        return deny("the agent doesn't change git metadata or CI workflows")
    if "test" in parts and "src" in parts and parts.index("test") == parts.index("src") + 1:
        return ALLOW  # src/test/** of the repo or of a module
    if parts[-1] in _SPECMATIC_FILES or parts[-1] in _BUILD_FILES:
        return ALLOW
    if config.allow_fixes and "main" in parts and "src" in parts:
        return ALLOW
    return deny(
        f"{target.relative_to(config.consumer)} is the consumer's own code. Don't change it: report "
        "the problem in consumer_bugs (run with --allow-fixes to let the agent fix it)"
    )


def _bash(command: str, config: AgentConfig) -> Decision:
    if not command.strip():
        return deny("empty command")
    if _SHELL_SYNTAX & set(command):
        return deny("one plain command only: no pipes, chains (&&, ;), redirects or $(...); "
                    "the working directory is already the consumer repo")  # fmt: skip
    try:
        words = shlex.split(command)
    except ValueError as exc:
        return deny(f"can't parse the command: {exc}")
    program = Path(words[0]).name
    if words[0] in (config.tcg, "tcg") or program == "tcg":
        return ALLOW if words[1:2] == ["index"] else deny("only `tcg index` is allowed; use the tcg MCP tools to read")
    if program in ("mvn", "mvnw", "gradle", "gradlew"):
        return ALLOW
    if program == "java":
        jar = words[2] if len(words) > 2 and words[1] == "-jar" else ""
        if jar and Path(jar).expanduser().resolve() == config.specmatic_jar:
            return ALLOW
        return deny(f"java is allowed only as: java -jar {config.specmatic_jar} ...")
    if program == "git" and words[1:2] and words[1] in _GIT_READ_ONLY:
        return ALLOW
    return deny(f"command not allowed: {program}. Allowed: tcg index, mvn/gradle, "
                f"java -jar {config.specmatic_jar}, git status/diff/log/show")  # fmt: skip


async def pre_tool_use_hook(config: AgentConfig, hook_input: dict[str, Any]) -> dict[str, Any]:
    """The PreToolUse hook body: deny with a reason the agent can act on, else let it run."""
    decision = decide(hook_input.get("tool_name", ""), hook_input.get("tool_input") or {}, config)
    if decision.allowed:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": decision.reason,
        }
    }

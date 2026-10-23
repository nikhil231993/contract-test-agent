"""`contract-agent <consumer>`: write and run Specmatic consumer contract tests for a service.

Exit codes: 0 the contract tests pass; 1 they fail or couldn't be written (see the report);
2 the run couldn't start or stopped early (bad setup, turn or budget limit, API error).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .agent import run
from .config import DEFAULT_MODEL, AgentConfig
from .report import render


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="contract-agent", description=__doc__.split("\n\n")[0])
    p.add_argument("consumer", type=Path, help="the consumer service's repo or module folder")
    p.add_argument("--specmatic-jar", type=Path, default=os.environ.get("SPECMATIC_JAR"),
                   help="the open-source Specmatic standalone jar (default: $SPECMATIC_JAR)")  # fmt: skip
    p.add_argument("--spec-repo", metavar="OWNER/REPO", help="where the provider specs live")
    p.add_argument("--work-dir", type=Path, help="scratch space (default: a temp folder)")
    p.add_argument("--allow-fixes", action="store_true",
                   help="let the agent fix consumer bugs the tests find (default: only report them)")  # fmt: skip
    p.add_argument("--tcg", default="tcg", help="test-context-graph CLI (default: tcg)")
    p.add_argument("--tcg-mcp", default="tcg-mcp", help="test-context-graph MCP server")
    p.add_argument("--ghes-mcp", default="ghes-openapi-mcp", help="spec finder MCP server")
    p.add_argument("--artifactory-mcp", help="provider-mocks MCP server (optional)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"default {DEFAULT_MODEL}; with --base-url, a model that server serves")  # fmt: skip
    p.add_argument("--base-url", default=os.environ.get("CONTRACT_AGENT_BASE_URL"),
                   help="an Anthropic-compatible server instead of the Claude API, e.g. Ollama at "
                        "http://localhost:11434 (default: $CONTRACT_AGENT_BASE_URL)")  # fmt: skip
    p.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--max-turns", type=int, default=120)
    p.add_argument("--budget", type=float, default=15.0, metavar="USD", help="stop at this cost (default 15)")
    p.add_argument("--note", action="append", default=[], help="extra instruction for the agent (repeatable)")
    p.add_argument("--report", type=Path, help="also write the JSON report here")
    p.add_argument("--quiet", action="store_true", help="no progress log")
    p.add_argument("--version", action="version", version=f"contract-agent {__version__}")
    return p.parse_args(argv)


def config_from(args: argparse.Namespace) -> AgentConfig:
    work_dir = args.work_dir or Path(tempfile.gettempdir()) / "contract-agent" / args.consumer.resolve().name
    return AgentConfig(
        consumer=args.consumer,
        specmatic_jar=args.specmatic_jar or Path("specmatic.jar"),
        work_dir=work_dir,
        tcg=args.tcg,
        tcg_mcp=args.tcg_mcp,
        ghes_mcp=args.ghes_mcp,
        artifactory_mcp=args.artifactory_mcp,
        spec_repo=args.spec_repo,
        allow_fixes=args.allow_fixes,
        model=args.model,
        base_url=args.base_url,
        effort=args.effort,
        max_turns=args.max_turns,
        budget_usd=args.budget,
        extra_notes=args.note,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = config_from(args)
    problems = config.check()
    if problems:
        for problem in problems:
            print(f"contract-agent: {problem}", file=sys.stderr)
        return 2
    log = (lambda _: None) if args.quiet else (lambda line: print(line, file=sys.stderr, flush=True))
    result = asyncio.run(run(config, log))
    if result.report is None:
        print(f"contract-agent: stopped ({result.subtype}) after {result.turns} turns, "
              f"${result.cost_usd or 0:.2f}: {'; '.join(result.errors) or 'no report'}", file=sys.stderr)  # fmt: skip
        return 2
    if args.report:
        args.report.write_text(json.dumps(result.report, indent=2) + "\n")
    print(render(result.report, result.cost_usd, result.turns))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())

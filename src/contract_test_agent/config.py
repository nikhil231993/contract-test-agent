"""What one run needs: the consumer repo, where the tools are, and the limits."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class AgentConfig:
    consumer: Path  # the consumer service's repo (or module folder): what gets contract tests
    specmatic_jar: Path  # the open-source Specmatic standalone jar
    work_dir: Path  # scratch space: the index, fetched specs. Outside the consumer repo.
    tcg: str = "tcg"  # test-context-graph's CLI
    tcg_mcp: str = "tcg-mcp"  # test-context-graph's MCP server
    ghes_mcp: str = "ghes-openapi-mcp"  # finds provider specs; reads its own .env
    artifactory_mcp: str | None = None  # finds existing WireMock stubs; optional
    spec_repo: str | None = None  # "owner/repo" holding the specs, if not ghes-openapi-mcp's default
    allow_fixes: bool = False  # may the agent fix the consumer's main code when a test shows a bug?
    model: str = DEFAULT_MODEL
    effort: str = "high"
    max_turns: int = 120
    budget_usd: float = 15.0
    extra_notes: list[str] = field(default_factory=list)  # free text added to the task

    def __post_init__(self) -> None:
        self.consumer = Path(self.consumer).resolve()
        self.specmatic_jar = Path(self.specmatic_jar).resolve()
        self.work_dir = Path(self.work_dir).resolve()

    @property
    def index_dir(self) -> Path:
        return self.work_dir / "index"

    @property
    def specs_dir(self) -> Path:
        return self.work_dir / "provider-specs"

    def check(self) -> list[str]:
        """Problems that would make the run fail early; [] when it can start."""
        problems = []
        if not (self.consumer / "pom.xml").is_file() and not any(self.consumer.glob("build.gradle*")):
            problems.append(f"{self.consumer} has no pom.xml or build.gradle: not a Java build")
        if not self.specmatic_jar.is_file():
            problems.append(f"Specmatic jar not found: {self.specmatic_jar}")
        if self.work_dir == self.consumer or self.consumer in self.work_dir.parents:
            problems.append("the work dir must be outside the consumer repo")
        for name, command in (("tcg", self.tcg), ("tcg-mcp", self.tcg_mcp), ("ghes-openapi-mcp", self.ghes_mcp),
                              ("artifactory-mocks-mcp", self.artifactory_mcp)):  # fmt: skip
            if command and shutil.which(command) is None:
                problems.append(f"{name} not found: {command} (install it or pass its path)")
        return problems

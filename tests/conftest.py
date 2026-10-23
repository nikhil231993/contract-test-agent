from pathlib import Path

import pytest

from contract_test_agent.config import AgentConfig


@pytest.fixture
def config(tmp_path: Path) -> AgentConfig:
    consumer = tmp_path / "checkout"
    (consumer / "src/main/java/org/shop").mkdir(parents=True)
    (consumer / "pom.xml").write_text("<project/>")
    jar = tmp_path / "tools" / "specmatic.jar"
    jar.parent.mkdir()
    jar.write_bytes(b"jar")
    return AgentConfig(consumer=consumer, specmatic_jar=jar, work_dir=tmp_path / "work")

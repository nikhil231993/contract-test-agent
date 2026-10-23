# contract-test-agent

An AI agent that writes **Specmatic consumer contract tests** for a Java Spring service, runs
them, and reports what it found, including bugs in the service itself.

```bash
contract-agent ~/code/checkout-consumer --spec-repo nikhil231993/contract-api-specs
```

It finds every HTTP call the service makes to other services, looks up each provider's OpenAPI
spec (the version marked ACTIVE), writes the Specmatic examples, `specmatic.yaml` and a JUnit
test that drives the service against a strict Specmatic mock, then runs the tests. A request the
contract doesn't allow fails the build: on the
[demo](https://github.com/nikhil231993/specmatic-contract-testing-demo) the first run caught
checkout sending `"amount": null` on full refunds.

## How it works

Built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk) (the Claude Code
harness as a library), with Claude Opus 5.5 and three MCP servers:

| Tool | What the agent uses it for |
|---|---|
| [test-context-graph](https://github.com/nikhil231993/test-context-graph) (`tcg`, `tcg-mcp`) | The service's outbound calls, each call's request as the code builds it, the base-URL property, entry points to drive, a draft example |
| [ghes-openapi-mcp](https://github.com/nikhil231993/ghes-openapi-mcp) | Finds the provider spec that defines a call, and its ACTIVE version |
| [artifactory-mocks-mcp](https://github.com/nikhil231993/artifactory-mocks-mcp) (optional) | Existing WireMock stubs, for realistic example values |
| [Specmatic](https://specmatic.io) (open source, jar) | Validates the config and examples, and is the strict mock the tests run against |

The workflow is in [`prompts.py`](src/contract_test_agent/prompts.py): index, list calls, find
and fetch each spec, re-index with it, get each call's context, write, validate, run, report.

## Safe to run unattended

Every tool call goes through [`guard.py`](src/contract_test_agent/guard.py) first:

- **Reads** stay in the service's repo and a scratch work dir.
- **Writes** go to `src/test/**`, `specmatic.yaml` and the build file (for the test
  dependency). The service's own code is off limits unless you pass `--allow-fixes`; by default a
  bug the tests find is **reported, not fixed**, and the tests keep failing on it.
- **Shell:** one plain command at a time from a short list: `tcg index`, `mvn`/`gradle`,
  `java -jar <the Specmatic jar>`, read-only `git`. No pipes, chains or redirects.
- No web access, no other MCP servers, no user or project settings: the same run everywhere.
- `--max-turns` and `--budget` (USD) stop a run that goes on too long.

## Install

Python 3.10+, Java 17 and Maven for the service's build.

```bash
uv venv && uv pip install -e .
uv pip install -e ../test-context-graph -e ../ghes-openapi-mcp   # the MCP servers, or put them on PATH
curl -sSLo specmatic.jar https://github.com/specmatic/specmatic/releases/download/2.55.3/specmatic-executable-all-2.55.3.jar
```

Credentials: `ANTHROPIC_API_KEY` for the model; ghes-openapi-mcp reads `GHES_BASE_URL` and
`GHES_TOKEN` from its environment or its own `.env` (`https://github.com` works for public repos).

## Run

```bash
export SPECMATIC_JAR=$PWD/specmatic.jar
contract-agent ../checkout-consumer --spec-repo nikhil231993/contract-api-specs --report report.json
```

Progress goes to stderr; the report (Markdown) to stdout, and as JSON with `--report`. Exit code
0: the contract tests pass. 1: they fail or couldn't be written (the report says why). 2: the run
couldn't start or hit a limit.

| Option | Default | |
|---|---|---|
| `--allow-fixes` | off | let it fix consumer bugs the tests find |
| `--artifactory-mcp CMD` | none | connect the provider-mocks server |
| `--budget USD` / `--max-turns N` | 15 / 120 | limits |
| `--model` / `--effort` | `claude-opus-5-5` / `high` | |
| `--base-url URL` | the Claude API | an Anthropic-compatible server, e.g. Ollama |
| `--note TEXT` | | an extra instruction (repeatable) |

## Local models (Ollama)

Any server that speaks the Anthropic Messages API works in place of the Claude API: Ollama
(v0.14+), llama.cpp, or a proxy. The agent, its tools and its guard stay the same.

```bash
ollama pull qwen3-coder:30b
contract-agent ../checkout-consumer --base-url http://localhost:11434 --model qwen3-coder:30b --budget 0
```

Pick a model with good tool calling and at least a 32K context. This is a long agentic coding
task: small local models tend to lose the thread, so check the report. `--budget` counts Claude
prices and means nothing for a local model.

## Development

```bash
.venv/bin/python -m pytest -q   # no API calls: the options, guard, prompts and report
```

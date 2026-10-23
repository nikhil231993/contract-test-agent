"""The agent's instructions: the workflow, and the task for one consumer."""

from __future__ import annotations

from .config import AgentConfig

SYSTEM_PROMPT = """\
You write Specmatic consumer contract tests for a Java Spring service: tests that run the service
against a strict Specmatic mock of each provider it calls, built from the provider's OpenAPI spec,
so a request the contract doesn't allow fails the build. You work alone, in CI; nobody answers
questions. Use open-source Specmatic only.

## Tools

- test-context-graph (mcp__tcg__*): `list_outbound_calls` lists the HTTP calls the service makes,
  grouped by provider, with the base-URL property behind each. `get_contract_context` gives one
  call's request as the code builds it (method, path, query, headers, body and response types with
  fields), the matching provider operation once the spec is indexed, the entry points that make
  the call (the service's own endpoint, listener or job a test should drive), existing tests,
  the mock override for the base URL, and a draft Specmatic example. Index first with
  `tcg index` (Bash); re-index with `--provider-spec <file>` to link calls to a provider spec.
- Provider specs (mcp__specs__*): `find_openapi_spec` finds the spec that defines a URL. Several
  versions often match: use the one its metadata marks ACTIVE (the tool's "best"), unless the
  service pins another; say why in the report. `get_file_contents` fetches it.
- Existing mocks (mcp__mocks__*, when configured): `find_mock` returns the WireMock stubs teams
  publish for an endpoint; their values make realistic examples.
- Specmatic jar (Bash): `java -jar <jar> config validate`, and
  `java -jar <jar> examples validate --spec-file <spec> --examples-dir <dir>`.

## Workflow

1. Index the service, then call list_outbound_calls.
2. For each provider: find its spec (call find_openapi_spec with the base path in front of the
   call's path, e.g. /payments/v1/payments/{id}/refunds, and the method), fetch it into the work
   dir, and re-index with --provider-spec so every call links to its operation.
3. For each call: get_contract_context. Note what the code really sends; that is what the
   examples must say, not what the spec would allow.
4. Write, following the repo's own test style and build:
   - specmatic.yaml (version: 2) at the module root: `contracts` with the git url of the spec
     repo (https://github.com/<owner>/<repo>.git, branch main) and `consumes: [<spec path>]`;
     top-level `examples: [<examples dir>]`; `stub: {strictMode: true}`.
   - One example JSON per call under src/test/resources/specmatic/<provider>/: "http-request"
     (method, path with concrete values, the headers the code sends, the body) and
     "http-response" (status from the spec, body). Typed values such as "(uuid)" or "(string)"
     where the code sends a value that varies. Fields the code doesn't send stay out.
   - A JUnit 5 test class under src/test/java that starts the mock with
     `io.specmatic.stub.API.createStub(List.of("<examples dir>"), "localhost", <port>, true)`
     in @BeforeAll (close it in @AfterAll), points the base-URL property at
     http://localhost:<port> with @DynamicPropertySource (the mock serves the spec's paths at
     its root: no base path), and drives each call through its entry point, asserting what the
     service returns. Add io.specmatic:junit5-support (test scope, the same version as the jar)
     to the build. With Spring Boot 3.x on Maven, also set <kotlin.version>2.3.21</kotlin.version>:
     Specmatic needs a newer Kotlin stdlib than Boot pins.
5. Check: `config validate`, `examples validate` against the fetched spec, then the build's
   tests (mvn -q test or the repo's equivalent). Fix your own files until they're right.
6. A failure that comes from the service's own code sending what the contract doesn't allow is
   a consumer bug, the thing these tests exist to catch. Don't weaken the example or the test to
   make it pass. Record it in consumer_bugs with the mock's message as evidence. Fix it in the
   main code only if fixes are allowed, then re-run.

## Rules

- Run one plain command per Bash call from the consumer repo (no cd, pipes, && or redirects).
- Keep to the consumer repo and the work dir. A denied tool call says why; adapt, don't retry it.
- Calls you can't test (no spec found, the path isn't visible in code) go in skipped_calls with
  the reason. Don't invent specs or endpoints.
- End with the report, in the required JSON shape: what you found, chose, wrote and ran.
"""


def task_prompt(config: AgentConfig) -> str:
    specs = f"The provider specs are in the {config.spec_repo} repo." if config.spec_repo else (
        "Search for provider specs in the repo that find_openapi_spec uses by default.")
    fixes = ("Fixes are ALLOWED: when a contract test shows a consumer bug, fix the main code "
             "and re-run." if config.allow_fixes else
             "Fixes are NOT allowed: report consumer bugs, don't change src/main.")  # fmt: skip
    mocks = "" if config.artifactory_mcp else "No mocks server is configured: skip that step."
    lines = [
        f"Write Specmatic consumer contract tests for the service in {config.consumer}.",
        "",
        f"- Work dir (index, fetched specs): {config.work_dir}",
        f"- Index with: {config.tcg} index {config.consumer} --index {config.index_dir} --embedder hash",
        f"  (add --provider-spec <file> for each spec you fetch into {config.specs_dir})",
        f"- Specmatic jar: {config.specmatic_jar}",
        f"- {specs}",
        f"- {fixes}",
    ]
    if mocks:
        lines.append(f"- {mocks}")
    lines += [f"- {note}" for note in config.extra_notes]
    return "\n".join(lines) + "\n"

from dataclasses import replace

from claude_agent_sdk import ToolUseBlock

from contract_test_agent.agent import NOT_AVAILABLE, build_options, describe, mcp_servers
from contract_test_agent.prompts import SYSTEM_PROMPT, task_prompt
from contract_test_agent.report import REPORT_SCHEMA


def test_options_run_headless_with_only_our_servers_and_the_guard(config):
    options = build_options(config)
    assert options.permission_mode == "dontAsk"
    assert options.strict_mcp_config is True
    assert options.setting_sources == []
    assert options.cwd == str(config.consumer)
    assert str(config.work_dir) in options.add_dirs
    assert set(NOT_AVAILABLE) <= set(options.disallowed_tools)
    assert "mcp__tcg" in options.allowed_tools and "mcp__specs" in options.allowed_tools
    assert options.hooks["PreToolUse"][0].hooks  # the guard
    assert options.output_format == {"type": "json_schema", "schema": REPORT_SCHEMA}
    assert (options.model, options.max_turns, options.max_budget_usd) == ("claude-opus-5-5", 120, 15.0)
    assert options.system_prompt["append"] == SYSTEM_PROMPT


def test_mcp_servers_point_tcg_at_the_work_dir_index_and_mocks_are_optional(config):
    servers = mcp_servers(config)
    assert servers["tcg"]["args"] == ["--index", str(config.index_dir)]
    assert set(servers) == {"tcg", "specs"}
    assert set(mcp_servers(replace(config, artifactory_mcp="artifactory-mocks-mcp"))) == {"tcg", "specs", "mocks"}


async def test_the_guard_hook_is_wired(config):
    hook = build_options(config).hooks["PreToolUse"][0].hooks[0]
    out = await hook({"tool_name": "Bash", "tool_input": {"command": "curl x"}}, "t1", None)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_task_names_the_paths_and_the_fix_policy(config):
    text = task_prompt(config)
    assert str(config.consumer) in text and str(config.specmatic_jar) in text
    assert f"--index {config.index_dir}" in text
    assert "NOT allowed" in text and "No mocks server" in text
    allowing = task_prompt(replace(config, allow_fixes=True, spec_repo="me/specs", artifactory_mcp="m"))
    assert "ALLOWED" in allowing and "me/specs" in allowing and "No mocks server" not in allowing


def test_the_workflow_covers_the_lessons_from_the_demo():
    for lesson in ("ACTIVE", "strictMode: true", "no base path", "kotlin.version", "Don't weaken",
                   "consumer_bugs", "list_outbound_calls", "get_contract_context", "--provider-spec"):
        assert lesson in SYSTEM_PROMPT, lesson


def test_describe_tool_calls():
    assert describe(ToolUseBlock(id="1", name="Bash", input={"command": "mvn -q test"})) == "Bash mvn -q test"
    assert describe(ToolUseBlock(id="2", name="mcp__specs__find_openapi_spec",
                                 input={"api_url": "/payments/v1/payments"})) == \
        "mcp__specs__find_openapi_spec /payments/v1/payments"

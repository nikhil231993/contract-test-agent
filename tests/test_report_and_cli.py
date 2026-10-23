import json

from contract_test_agent import cli
from contract_test_agent.agent import RunResult
from contract_test_agent.report import REPORT_SCHEMA, render

REPORT = {
    "status": "failed",
    "summary": "Checkout's refund call breaks the Payments contract.",
    "providers": [{
        "base_url_property": "payments.api.url", "spec_repo": "me/specs",
        "spec_path": "payments/apis/CMPayments_v1.14.yaml", "spec_version": "1.14.0",
        "why_this_version": "ACTIVE in its metadata",
        "calls": [{"call": "POST /payments/{paymentId}/refunds", "example_files": ["refund.json"],
                   "test": "PaymentsConsumerContractTest#refund"}],
    }],
    "files_written": ["specmatic.yaml"],
    "test_run": {"command": "mvn -q test", "passed": 2, "failed": 1, "output_excerpt": "REQUEST.BODY.amount"},
    "consumer_bugs": [{"description": "sends amount: null", "evidence": "R1001", "location": "RefundRequest.java",
                       "fixed": False}],
    "skipped_calls": [],
    "notes": [],
}


def test_the_schema_requires_every_section():
    assert set(REPORT_SCHEMA["required"]) == set(REPORT)


def test_render():
    text = render(REPORT, 1.234, 42)
    assert "## Contract tests: failed" in text
    assert "v1.14.0" in text and "2 passed, 1 failed" in text
    assert "Consumer bug** (not fixed)" in text and "42 turns, $1.23" in text


def test_a_bad_setup_exits_2_before_any_api_call(tmp_path, capsys):
    assert cli.main([str(tmp_path), "--specmatic-jar", str(tmp_path / "none.jar")]) == 2
    err = capsys.readouterr().err
    assert "not a Java build" in err and "Specmatic jar not found" in err


def run_cli(monkeypatch, config, result, *extra):
    async def fake_run(cfg, log):
        assert cfg.consumer == config.consumer
        return result
    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli.AgentConfig, "check", lambda self: [])
    return cli.main([str(config.consumer), "--specmatic-jar", str(config.specmatic_jar), "--quiet", *extra])


def test_exit_codes_follow_the_report(monkeypatch, config, tmp_path, capsys):
    report_file = tmp_path / "r.json"
    assert run_cli(monkeypatch, config, RunResult(report=REPORT, subtype="success"), "--report", str(report_file)) == 1
    assert json.loads(report_file.read_text())["status"] == "failed"
    assert "Contract tests: failed" in capsys.readouterr().out
    passed = {**REPORT, "status": "passed", "consumer_bugs": []}
    assert run_cli(monkeypatch, config, RunResult(report=passed, subtype="success")) == 0
    stopped = RunResult(report=None, subtype="error_max_budget_usd", cost_usd=15.2, turns=60)
    assert run_cli(monkeypatch, config, stopped) == 2
    assert "error_max_budget_usd" in capsys.readouterr().err

from bughound_agent import BugHoundAgent
from llm_client import MockClient


class _BadSeverityClient:
    """Returns well-formed JSON whose severity violates the analyzer contract."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:  # analyzer prompt
            return '[{"type": "Reliability", "severity": "catastrophic", "msg": "bare except"}]'
        return "def f():\n    return True\n"  # fixer prompt: return something harmless


def test_workflow_runs_in_offline_mode_and_returns_shape():
    agent = BugHoundAgent(client=None)  # heuristic-only
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert isinstance(result, dict)
    assert "issues" in result
    assert "fixed_code" in result
    assert "risk" in result
    assert "logs" in result

    assert isinstance(result["issues"], list)
    assert isinstance(result["fixed_code"], str)
    assert isinstance(result["risk"], dict)
    assert isinstance(result["logs"], list)
    assert len(result["logs"]) > 0


def test_offline_mode_detects_print_issue():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])


def test_offline_mode_proposes_logging_fix_for_print():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    fixed = result["fixed_code"]
    assert "logging" in fixed
    assert "logging.info(" in fixed


def test_mock_client_forces_llm_fallback_to_heuristics_for_analysis():
    # MockClient returns non-JSON for analyzer prompts, so agent should fall back.
    agent = BugHoundAgent(client=MockClient())
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    # Ensure we logged the fallback path
    assert any("Falling back to heuristics" in entry.get("message", "") for entry in result["logs"])


def test_invalid_severity_from_llm_falls_back_to_heuristics():
    # Guardrail: parseable JSON with an out-of-contract severity must be
    # rejected so unknown severities don't silently understate risk.
    agent = BugHoundAgent(client=_BadSeverityClient())
    code = "def load(path):\n    try:\n        return open(path).read()\n    except:\n        return None\n"
    result = agent.run(code)

    # The bogus "catastrophic" issue must not survive...
    assert all(
        str(i.get("severity", "")).lower() in {"low", "medium", "high"}
        for i in result["issues"]
    )
    # ...and the agent must have logged the severity-based fallback.
    assert any(
        "invalid severity" in entry.get("message", "").lower()
        for entry in result["logs"]
    )
    # Heuristics should still catch the bare except in this snippet.
    assert any(i.get("type") == "Reliability" for i in result["issues"])

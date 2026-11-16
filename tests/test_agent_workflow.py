from bughound_agent import BugHoundAgent
from llm_client import MockClient


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


class _StubClient:
    def __init__(self, analyzer_reply):
        self.analyzer_reply = analyzer_reply

    def complete(self, system_prompt, user_prompt):
        if "Return ONLY valid JSON" in system_prompt:
            return self.analyzer_reply
        return "def f():\n    return True\n"


CODE = "def f():\n    print('hi')\n    return True\n"


def test_wrong_shape_items_fall_back_to_heuristics():
    result = BugHoundAgent(client=_StubClient('[{"foo": 1}]')).run(CODE)
    assert any(i["type"] == "Code Quality" for i in result["issues"])
    assert not any(i["type"] == "Issue" for i in result["issues"])
    assert any("Falling back to heuristics" in e["message"] for e in result["logs"])


def test_bad_severity_dropped_and_valid_kept():
    reply = '[{"type":"A","severity":"Critical","msg":"x"},{"type":"B","severity":"high","msg":"y"}]'
    result = BugHoundAgent(client=_StubClient(reply)).run(CODE)
    assert result["issues"] == [{"type": "B", "severity": "High", "msg": "y"}]


def test_empty_array_is_accepted_without_fallback():
    result = BugHoundAgent(client=_StubClient("[]")).run(CODE)
    assert result["issues"] == []
    assert not any("Falling back" in e["message"] for e in result["logs"])


def test_identifier_ending_in_print_is_not_flagged_or_rewritten():
    code = "def f(x):\n    footprint(x)\n    return x\n"
    result = BugHoundAgent(client=None).run(code)
    assert not any(i["type"] == "Code Quality" for i in result["issues"])
    assert result["fixed_code"] == code


def test_only_real_print_is_rewritten_when_mixed_with_pprint():
    code = "def f(x):\n    pprint(x)\n    print(x)\n    return x\n"
    fixed = BugHoundAgent(client=None).run(code)["fixed_code"]
    assert "pprint(x)" in fixed
    assert "logging.info(x)" in fixed
    assert "plogging" not in fixed


def test_guardrail_no_corrupting_fix_or_false_confidence_on_footprint():
    # Decision-level check for the print-call guardrail (offline, no API).
    # Without it, `footprint(` was rewritten to `footlogging.info(` and scored
    # 95 / low with auto-fix approved for a fix that breaks the code.
    code = "def f(x):\n    footprint(x)\n    return x\n"
    result = BugHoundAgent(client=None).run(code)

    assert "footlogging" not in result["fixed_code"]
    assert result["issues"] == []
    assert result["risk"]["reasons"] == ["No significant risks detected."]
    assert result["risk"]["score"] == 100

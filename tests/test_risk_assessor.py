from reliability.risk_assessor import assess_risk


def test_no_fix_is_high_risk():
    risk = assess_risk(
        original_code="print('hi')\n",
        fixed_code="",
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "print"}],
    )
    assert risk["level"] == "high"
    assert risk["should_autofix"] is False
    assert risk["score"] == 0


def test_low_risk_when_minimal_change_and_low_severity():
    original = "import logging\n\ndef add(a, b):\n    return a + b\n"
    fixed = "import logging\n\ndef add(a, b):\n    return a + b\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "minor"}],
    )
    assert risk["level"] in ("low", "medium")  # depends on scoring rules
    assert 0 <= risk["score"] <= 100


def test_high_severity_issue_drives_score_down():
    original = "def f():\n    try:\n        return 1\n    except:\n        return 0\n"
    fixed = "def f():\n    try:\n        return 1\n    except Exception as e:\n        return 0\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Reliability", "severity": "High", "msg": "bare except"}],
    )
    assert risk["score"] <= 60
    assert risk["level"] in ("medium", "high")


def test_missing_return_is_penalized():
    original = "def f(x):\n    return x + 1\n"
    fixed = "def f(x):\n    x + 1\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[],
    )
    assert risk["score"] < 100
    assert any("Return" in r or "return" in r for r in risk["reasons"])


def test_structural_change_blocks_autofix_even_when_risk_is_low():
    """
    Guardrail: a fix that changes code structure must defer to human review,
    even if the numeric risk score lands in the "low" band.

    A single low-severity issue plus a bare-except rewrite scores 90 ("low"),
    which the OLD policy (should_autofix = level == "low") would have
    auto-applied. The tightened policy must refuse.
    """
    original = "def f(x):\n    try:\n        return 1 / x\n    except:\n        return 0\n"
    fixed = "def f(x):\n    try:\n        return 1 / x\n    except Exception as e:\n        return 0\n"
    issues = [{"type": "Code Quality", "severity": "Low", "msg": "print"}]

    risk = assess_risk(original_code=original, fixed_code=fixed, issues=issues)

    assert risk["level"] == "low"          # score stays in the low band...
    assert risk["should_autofix"] is False  # ...but auto-fix is still refused
    assert any("except" in r.lower() for r in risk["reasons"])


def test_low_risk_fix_without_structural_change_still_autofixes():
    """
    Counterpart: the tightened gate must not over-block. A low-severity fix
    that preserves length, returns, and error handling should still auto-apply.
    """
    original = "def add(a, b):\n    print('adding')\n    return a + b\n"
    fixed = "import logging\n\ndef add(a, b):\n    logging.info('adding')\n    return a + b\n"
    issues = [{"type": "Code Quality", "severity": "Low", "msg": "print"}]

    risk = assess_risk(original_code=original, fixed_code=fixed, issues=issues)

    assert risk["level"] == "low"
    assert risk["should_autofix"] is True

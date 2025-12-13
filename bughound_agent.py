import json
import re
from typing import Any, Dict, List, Optional, Tuple

from reliability.risk_assessor import assess_risk


class BugHoundAgent:
    """
    BugHound runs a small agentic workflow:

    1) PLAN: decide what to look for
    2) ANALYZE: detect issues (heuristics or LLM)
    3) ACT: propose a fix (heuristics or LLM)
    4) TEST: run simple reliability checks
    5) REFLECT: decide whether to apply the fix automatically
    """

    def __init__(self, client: Optional[Any] = None):
        # client should implement: complete(system_prompt: str, user_prompt: str) -> str
        # In heuristic-only mode, a MockClient can be passed in, but the agent also
        # supports running fully via local heuristics.
        self.client = client
        self.logs: List[Dict[str, str]] = []

    # ----------------------------
    # Public API
    # ----------------------------
    def run(self, code_snippet: str) -> Dict[str, Any]:
        self.logs = []
        self._log("PLAN", "Planning a quick scan + fix proposal workflow.")

        issues = self.analyze(code_snippet)
        self._log("ANALYZE", f"Found {len(issues)} issue(s).")

        fixed_code = self.propose_fix(code_snippet, issues)
        if fixed_code.strip() == "":
            self._log("ACT", "No fix produced (refused, error, or empty output).")

        risk = assess_risk(original_code=code_snippet, fixed_code=fixed_code, issues=issues)
        self._log("TEST", f"Risk assessed as {risk.get('level', 'unknown')} (score={risk.get('score', '-')}).")

        # Optional reflection: for now, treat the risk policy as the final decision.
        if risk.get("should_autofix"):
            self._log("REFLECT", "Fix appears safe enough to auto-apply under current policy.")
        else:
            self._log("REFLECT", "Fix is not safe enough to auto-apply. Human review recommended.")

        return {
            "issues": issues,
            "fixed_code": fixed_code,
            "risk": risk,
            "logs": self.logs,
        }

    # ----------------------------
    # Workflow steps
    # ----------------------------
    def analyze(self, code_snippet: str) -> List[Dict[str, str]]:
        """
        Returns a list of issues with keys:
        - type: str
        - severity: str (Low/Medium/High)
        - msg: str
        """
        # If no LLM client, or if using a MockClient, fall back to heuristics.
        if not self._can_call_llm():
            self._log("ANALYZE", "Using heuristic analyzer (offline mode).")
            return self._heuristic_analyze(code_snippet)

        self._log("ANALYZE", "Using LLM analyzer.")
        system_prompt = (
            "You are BugHound, a code review assistant. "
            "Return ONLY valid JSON. No markdown, no backticks."
        )
        user_prompt = (
            "Analyze this Python code for potential issues. "
            "Return a JSON array of issue objects with keys: type, severity, msg.\n\n"
            f"CODE:\n{code_snippet}"
        )

        raw = self.client.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        issues = self._parse_json_array_of_issues(raw)

        # If parsing fails, degrade gracefully to heuristics so the lab still works.
        if issues is None:
            self._log("ANALYZE", "LLM output was not parseable JSON. Falling back to heuristics.")
            return self._heuristic_analyze(code_snippet)

        return issues

    def propose_fix(self, code_snippet: str, issues: List[Dict[str, str]]) -> str:
        """
        Returns a rewritten code snippet as a string.
        """
        if not issues:
            self._log("ACT", "No issues, returning original code unchanged.")
            return code_snippet

        if not self._can_call_llm():
            self._log("ACT", "Using heuristic fixer (offline mode).")
            return self._heuristic_fix(code_snippet, issues)

        self._log("ACT", "Using LLM fixer.")
        system_prompt = (
            "You are BugHound, a careful refactoring assistant. "
            "Return ONLY the full rewritten Python code. No markdown, no backticks."
        )
        user_prompt = (
            "Rewrite the code to address the issues listed. "
            "Preserve behavior when possible. Keep changes minimal.\n\n"
            f"ISSUES (JSON):\n{json.dumps(issues)}\n\n"
            f"CODE:\n{code_snippet}"
        )

        raw = self.client.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        cleaned = self._strip_code_fences(raw).strip()

        # Safety: if the model returns something empty, fall back to heuristics.
        if not cleaned:
            self._log("ACT", "LLM returned empty output. Falling back to heuristic fixer.")
            return self._heuristic_fix(code_snippet, issues)

        return cleaned

    # ----------------------------
    # Heuristic analyzer/fixer
    # ----------------------------
    def _heuristic_analyze(self, code: str) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []

        if "print(" in code:
            issues.append(
                {
                    "type": "Code Quality",
                    "severity": "Low",
                    "msg": "Found print statements. Consider using logging for non-toy code.",
                }
            )

        if re.search(r"\bexcept\s*:\s*(\n|#|$)", code):
            issues.append(
                {
                    "type": "Reliability",
                    "severity": "High",
                    "msg": "Found a bare `except:`. Catch a specific exception or use `except Exception as e:`.",
                }
            )

        if "TODO" in code:
            issues.append(
                {
                    "type": "Maintainability",
                    "severity": "Medium",
                    "msg": "Found TODO comments. Unfinished logic can hide bugs or missing cases.",
                }
            )

        return issues

    def _heuristic_fix(self, code: str, issues: List[Dict[str, str]]) -> str:
        fixed = code

        # Fix bare except first (high risk).
        if any(i.get("type") == "Reliability" for i in issues):
            fixed = re.sub(r"\bexcept\s*:\s*", "except Exception as e:\n        # [BugHound] log or handle the error\n        ", fixed)

        # Replace print with logging.info (simple, imperfect, good for a tinker).
        if any(i.get("type") == "Code Quality" for i in issues):
            if "import logging" not in fixed:
                fixed = "import logging\n\n" + fixed
            fixed = fixed.replace("print(", "logging.info(")

        # Leave TODOs as is (a “fix” might be to make TODO visible, not guess intent).
        return fixed

    # ----------------------------
    # Parsing + utilities
    # ----------------------------
    def _parse_json_array_of_issues(self, text: str) -> Optional[List[Dict[str, str]]]:
        """
        Try to parse a JSON array. If the model outputs extra text, attempt to extract
        the first JSON array substring.
        """
        text = text.strip()

        # Fast path: direct JSON
        parsed = self._try_json_loads(text)
        if isinstance(parsed, list):
            normalized = self._normalize_issues(parsed)
            return normalized

        # Attempt to extract a JSON array from messy output
        array_str = self._extract_first_json_array(text)
        if array_str:
            parsed2 = self._try_json_loads(array_str)
            if isinstance(parsed2, list):
                return self._normalize_issues(parsed2)

        return None

    def _normalize_issues(self, arr: List[Any]) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            issues.append(
                {
                    "type": str(item.get("type", "Issue")),
                    "severity": str(item.get("severity", "Unknown")),
                    "msg": str(item.get("msg", "")).strip(),
                }
            )
        return issues

    def _try_json_loads(self, s: str) -> Any:
        try:
            return json.loads(s)
        except Exception:
            return None

    def _extract_first_json_array(self, s: str) -> Optional[str]:
        """
        Best-effort extraction of the first [...] substring that looks like JSON.
        """
        start = s.find("[")
        if start == -1:
            return None

        depth = 0
        for i in range(start, len(s)):
            if s[i] == "[":
                depth += 1
            elif s[i] == "]":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        return None

    def _strip_code_fences(self, text: str) -> str:
        """
        Remove ``` fences if the model includes them anyway.
        """
        text = text.strip()
        # Remove triple-backtick fenced blocks, keep inner content.
        match = re.search(r"```(?:python)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)
        return text

    def _can_call_llm(self) -> bool:
        return self.client is not None and hasattr(self.client, "complete")

    def _log(self, step: str, message: str) -> None:
        self.logs.append({"step": step, "message": message})

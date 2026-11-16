# BugHound Mini Model Card (Reflection)

Fill this out after you run BugHound in **both** modes (Heuristic and Gemini).

---

## 1) What is this system?

**Name:** BugHound  
**Purpose:** Analyze a Python snippet, propose a fix, and run reliability checks before suggesting whether the fix should be auto-applied.

**Intended users:** Students learning agentic workflows and AI reliability concepts.

---

## 2) How does it work?

Describe the workflow in your own words (plan → analyze → act → test → reflect).  
Include what is done by heuristics vs what is done by Gemini (if enabled).

---

## 3) Inputs and outputs

**Inputs:**

- What kind of code snippets did you try?
- What was the “shape” of the input (short scripts, functions, try/except blocks, etc.)?

**Outputs:**

- What types of issues were detected?
- What kinds of fixes were proposed?
- What did the risk report show?

---

## 4) Reliability and safety rules

List at least **two** reliability rules currently used in `assess_risk`. For each:

- What does the rule check?
- Why might that check matter for safety or correctness?
- What is a false positive this rule could cause?
- What is a false negative this rule could miss?

---

## 5) Observed failure modes

Provide at least **two** examples:

1. A time BugHound missed an issue it should have caught  
2. A time BugHound suggested a fix that felt risky, wrong, or unnecessary  

For each, include the snippet (or describe it) and what went wrong.

**Failure mode found and fixed: identifier corruption with unsafe confidence.**
- Snippet: `def f(x):\n    footprint(x)\n    return x\n` (heuristic mode).
- What went wrong: the print detector used `"print(" in code` and the fixer used `str.replace`, so `footprint(` was flagged and rewritten to `footlogging.info(`, an undefined name. The result still parsed, kept `return` and its length, so `assess_risk` scored it 95 / low and allowed auto-fix. It would raise `NameError` at runtime.
- Fix: both steps now use `\bprint\(` (`_PRINT_CALL` in `bughound_agent.py`). Guardrail placed in the agent workflow, since the false positive is the root cause; a general "undefined names" check in `assess_risk` would need symbol analysis. Regression tests are in `tests/test_agent_workflow.py`.
- Before: issue reported, code rewritten, 95 low, auto-fix True. After: no issue, code unchanged, 100 low. Sample files unchanged (cleanish 100, mixed_issues 30, print_spam 95).
- Still open: a literal `print(` inside a string or comment is still flagged and rewritten (needs tokenizing). Comments-only files with a `TODO` also report auto-fix True although nothing changes, and an empty file reports "No fix was produced" at score 0.

---

## 6) Heuristic vs Gemini comparison

Compare behavior across the two modes:

- What did Gemini detect that heuristics did not?
- What did heuristics catch consistently?
- How did the proposed fixes differ?
- Did the risk scorer agree with your intuition?

---

## 7) Human-in-the-loop decision

Describe one scenario where BugHound should **refuse** to auto-fix and require human review.

- What trigger would you add?
- Where would you implement it (risk_assessor vs agent workflow vs UI)?
- What message should the tool show the user?

---

## 8) Improvement idea

Propose one improvement that would make BugHound more reliable *without* making it dramatically more complex.

Examples:

- A better output format and parsing strategy
- A new guardrail rule + test
- A more careful “minimal diff” policy
- Better detection of changes that alter behavior

Write your idea clearly and briefly.

**My improvement:** Strictly validate the LLM's analyzer output (schema and severity checks, with a logged fallback to heuristics). See the section below.


---

## Reliability change: strict validation of LLM analyzer output

**What changed:** `_normalize_issues` in `bughound_agent.py` used to accept any JSON array and fill in defaults for missing fields (`"Issue"`, `"Unknown"`, `""`). It now requires each item to have a non-empty `type` and `msg` and a `severity` of Low, Medium or High (case-insensitive). Invalid items are dropped and logged. If the array is non-empty but no item is valid, `analyze()` falls back to the heuristic analyzer and logs why. A genuine `[]` is still accepted as "no issues".

**Why:** Output that was valid JSON but the wrong shape passed silently as "valid". Placeholder issues then flowed into `propose_fix` and `assess_risk` and skewed the risk score, with no log entry.

**Before/after (same input, replayed through a stub client, not live Gemini):**
Input snippet: `def f(): print('hi'); return True`. Model reply: `[{"foo": 1}]`.

| | Issues returned | Risk score | Log |
|---|---|---|---|
| Before | `Issue / Unknown / ""` (placeholder) | 100 | none |
| After | heuristic `Code Quality / Low` (print statement) | 95 | schema validation failed, falling back to heuristics |

**Trade-offs:** Slightly off output, such as an unknown severity like "Critical", is now dropped instead of kept. When every item is invalid, the model's findings are replaced by heuristic ones, so those runs lose any insight only the model had. Tests are in `tests/test_agent_workflow.py`. This was verified with stub clients only, with no live Gemini run.


---

## Risk signal change: fixed code must still parse

**What changed:** `assess_risk` in `reliability/risk_assessor.py` now runs `ast.parse` on the proposed fix. If the original code parses but the fix does not, the score drops by 50, the reason "Fixed code does not parse as valid Python." is added, and `should_autofix` is forced to `False`. An original that already fails to parse is not penalized.

**Why:** No existing rule checked that the fix was valid Python. A model-written fix with a syntax error that kept `return` and a similar length scored as low risk and was auto-applied.

**Before/after (same input, direct `assess_risk` call, no Gemini):**
Original: `def f(): print('hi'); return True`. Fix: `def f(:` (syntax error). One Low issue.

| | Score | Level | Auto-fix | Reasons |
|---|---|---|---|---|
| Before | 95 | low | True | Low severity issue detected |
| After | 45 | medium | False | Low severity issue detected; Fixed code does not parse as valid Python |

**Regression check:** The four `sample_code/*.py` files in heuristic mode score identically before and after (cleanish 100, flaky_try_except 55, mixed_issues 30, print_spam 95), because heuristic fixes always compile. The signal only affects model-written fixes.

**Limits:** `ast.parse` checks syntax only, not behavior, so a fix that parses but changes logic is still not caught. Snippets that are valid fragments but not valid modules could be flagged, which is why the check applies only when the original parses. Not yet seen firing on a live Gemini fix. Tests are in `tests/test_risk_assessor.py`.

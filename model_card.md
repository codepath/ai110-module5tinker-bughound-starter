# BugHound Mini Model Card (Reflection)

> Status note: Heuristic / offline mode was run and driven end-to-end.
> Gemini mode was **not** executed live because a real `GEMINI_API_KEY` has
> not been supplied yet — the `.env` still holds the placeholder. Sections that
> describe Gemini behavior are grounded in the prompt contracts and agent code,
> and are marked **(predicted)** where they were not directly observed.

---

## 1) What is this system?

**Name:** BugHound
**Purpose:** Analyze a Python snippet, detect issues, propose a fix, assess the
risk of that fix, and decide whether it is safe to auto-apply or should be
deferred to a human.

**Intended users:** Students learning agentic workflows and AI-reliability
concepts. Not a production linter — a teaching harness for how an agent makes
(and guards) decisions.

---

## 2) How does it work?

BugHound runs a fixed five-step loop (`BugHoundAgent.run`):

1. **PLAN** — logs the intent to scan and propose a fix. No real branching.
2. **ANALYZE** — detect issues. Uses the LLM path if a client with a
   `complete()` method is present, otherwise heuristics. The LLM result is
   parsed as a JSON array and validated; on any parse failure **or an
   out-of-contract severity**, it falls back to `_heuristic_analyze`.
3. **ACT** — `propose_fix`. If there are no issues, returns the code
   unchanged. Otherwise LLM fixer or heuristic fixer, with fallback on error
   or empty output.
4. **TEST** — `assess_risk` scores the change from 100 downward and maps it to
   low / medium / high.
5. **REFLECT** — logs whether the fix is safe to auto-apply under policy.

**Heuristics vs. Gemini:**
- *Heuristics* are pure string/regex rules: detects `print(`, bare `except:`,
  and `TODO`; fixes by adding `logging` and widening bare excepts.
- *Gemini* is treated as a **tool the agent calls**, not a replacement. The
  agent still owns parsing, validation, fallback, risk scoring, and the
  auto-fix decision. A bad model response degrades to heuristics rather than
  failing.

A subtle but important detail: `_can_call_llm()` returns true for **any**
client with a `complete()` method — including the offline `MockClient`. So in
"Heuristic only" mode the trace actually reads *"Using LLM analyzer / fixer"*
and then falls back. Offline mode is really "LLM path with a mock that forces
fallback," not a separate code path.

---

## 3) Inputs and outputs

**Inputs tried (from `sample_code/` and inline):**
- `mixed_issues.py`-style function: `compute(x, y)` with a `print`, a
  `try/except`, and a bare `except:` returning `0`. Short function, ~6 lines.
- Shape: small self-contained functions, typically containing a `try/except`
  block and/or `print` statements.

**Outputs observed (offline run on `compute(x, y)`):**
- **Detected issues:** `Code Quality | Low` (print statements) and
  `Reliability | High` (bare `except:`).
- **Proposed fix:** In offline mode the "fix" was the MockClient placeholder
  `# MockClient: no rewrite available in offline mode.` — the diff showed the
  **entire function was deleted**.
- **Risk report:** score **0**, level **HIGH**, auto-fix **NO**, with reasons:
  high-severity issue, low-severity issue, fixed code much shorter, returns
  possibly removed, bare except modified.
- **Trace:** PLAN → ANALYZE (LLM → fallback) → ACT → TEST (high, score 0) →
  REFLECT ("not safe enough to auto-apply, human review recommended").

---

## 4) Reliability and safety rules

**Rule A — "Return statements may have been removed"**
(`"return" in original and "return" not in fixed` → −30)
- *Checks:* whether the fix dropped all `return` statements.
- *Why it matters:* losing a return silently changes a function's output
  contract — a high-impact behavioral change.
- *False positive:* a legitimate refactor that replaces `return x` with a
  single `raise` or restructures control flow would be penalized even though
  behavior is arguably fine.
- *False negative:* substring matching only checks *presence*. A fix that
  removes 3 of 4 returns, or keeps a `# return later` comment, passes clean.

**Rule B — Auto-fix gate (tightened in this activity)**
(`should_autofix = level == "low" and not structural_change`)
- *Checks:* only auto-apply when risk is low **and** no structural change was
  detected (length halved, returns removed, or bare-except modified).
- *Why it matters:* a low numeric score is not the same as "safe." Edits that
  touch control flow or error handling deserve human eyes even when the score
  looks benign.
- *False positive:* a purely cosmetic fix that happens to trip a structural
  flag (e.g. a good `except:` → `except Exception` rewrite) is now sent to
  human review even though it is desirable. This is an intentional, cautious
  trade-off.
- *False negative:* structural detection is still string-based, so a
  behavior-changing edit that keeps line count, keeps a `return`, and doesn't
  remove a bare except would not set the flag and could still auto-apply.

---

## 5) Observed failure modes

1. **Over-editing / unusable fix accepted (observed).** In offline mode the
   MockClient returned `# MockClient: no rewrite available in offline mode.`
   `propose_fix` only checks that output is **non-empty**, so this placeholder
   was accepted as the "fix," wiping the entire function. Only the risk layer
   (HIGH → no auto-fix) prevented harm. The acceptance check in the ACT step is
   too weak to notice that a "fix" destroyed the code.

2. **Risk under-counting from unvalidated severity (observed via code +
   test).** `assess_risk` only deducts points for severities that are exactly
   low/medium/high; any other string deducts **0**. The analyzer originally
   accepted whatever severity the model returned, so a malformed AI response
   (e.g. severity `"catastrophic"`) would pass through and be scored as *zero
   risk* — understating danger. This was reproduced with a fake client in a
   test and is the motivation for the Part 2 severity guardrail.

---

## 6) Heuristic vs Gemini comparison

- **Heuristics caught consistently (observed):** `print(`, bare `except:`, and
  `TODO`. Deterministic, no network, but blind to anything outside those three
  patterns (e.g. resource leaks, mutable default args, swallowed exceptions
  with logic).
- **Gemini expected to add (predicted):** semantic issues the regexes cannot
  see — e.g. that `except: return 0` *silently hides* a `ZeroDivisionError`,
  unclosed file handles in `open(path).read()`, or missing input validation.
  The analyzer prompt asks for reliability/maintainability/correctness/
  readability, so its issue set should be broader and more contextual.
- **Fixes differ (predicted):** the heuristic fixer does blunt string
  substitution (`print(` → `logging.info(`, widen bare except); Gemini is
  prompted to "preserve behavior" and "make the smallest changes," so its
  diffs should be more targeted — but are only as trustworthy as the risk
  layer that checks them.
- **Did the risk scorer match intuition?** For the destroyed-code case, yes —
  HIGH was correct. But it agrees for the wrong reason (line-count/return
  heuristics), not because it understood the code changed behavior.

*(To complete this section with real data: add your key to `.env`, switch to
Gemini mode, and run two `sample_code/` files. Each run uses one of ~20 daily
free-tier requests.)*

---

## 7) Human-in-the-loop decision

**Scenario:** A fix that modifies error handling or removes/relocates control
flow (e.g. rewriting a `try/except`, dropping a `return`, or shortening the
function significantly) should never auto-apply, regardless of how low the
numeric score is.

- **Trigger:** any `structural_change` signal in `assess_risk`.
- **Where implemented:** in `reliability/risk_assessor.py` (done in this
  activity) — `should_autofix = level == "low" and not structural_change`.
  Keeping it in the risk layer means every caller (UI, tests, future
  automation) inherits the guard, rather than trusting each entry point to
  re-check.
- **Message to user:** "This fix changes control flow or error handling.
  Auto-apply is disabled — please review the diff before accepting."

---

## 8) Improvement idea

**Strengthen the ACT-step acceptance check.** `propose_fix` currently accepts
any non-empty string as a valid fix, which is how the MockClient placeholder
(and, in principle, an LLM apology or prose response) got accepted as code. A
low-complexity guardrail: before returning the fix, verify it is plausibly the
same program — e.g. it parses as valid Python (`ast.parse`) and still defines
the same top-level function/class names as the original. If not, log the
rejection and fall back to the heuristic fixer (or return the original code
unchanged). This closes the gap that the risk layer currently has to
compensate for, and is easily covered by an offline test with a mock client
that returns non-code text.

# BugHound Mini Model Card (Reflection)

Completed from heuristic-mode and stub-client runs. **Gemini mode was not run live**; see section 6.

---

## 1) What is this system?

**Name:** BugHound  
**Purpose:** Analyze a Python snippet, propose a fix, and run reliability checks before suggesting whether the fix should be auto-applied.

**Intended users:** Students learning agentic workflows and AI reliability concepts.

**Not intended for:** unattended modification of real code. It is a teaching tool with a small rule set; a human should review every fix.

---

## 2) How does it work?

`BugHoundAgent.run()` in `bughound_agent.py` runs five steps:

1. **Plan:** logs that it will do a scan plus fix proposal. No decision is made here.
2. **Analyze:** finds issues. With no client it uses the heuristic analyzer (regex checks for `print(` calls, bare `except:`, and `TODO`). With a client it asks the model for a JSON array of `{type, severity, msg}`. If the API errors, the reply isn't a JSON array, or no item passes schema validation, it falls back to the heuristic analyzer and logs the reason.
3. **Act:** `propose_fix` returns the code unchanged if there are no issues. Otherwise the heuristic fixer (regex rewrites) or the model rewrites the code. Empty output or an API error falls back to the heuristic fixer. Markdown fences are stripped from model output.
4. **Test:** `assess_risk` in `reliability/risk_assessor.py` scores the fix from 0 to 100 using issue severity and a few structural checks.
5. **Reflect:** `should_autofix` is true only when the level is `low` (score 75 or more) and the fix still parses. Otherwise the trace says human review is recommended.

**Heuristics vs Gemini:** In heuristic mode both analysis and fixing are rule-based and deterministic. In Gemini mode both are model calls (two per run), with heuristics as the fallback. The risk step is always rule-based.

---

## 3) Inputs and outputs

**Inputs:** The four files in `sample_code/` (5-9 lines each: small functions, one try/except, print calls), plus crafted snippets: an empty file, a comments-only file with a `TODO`, `footprint(x)`, a string containing `print(`, and a mutable-default plus `except Exception: pass` function.

**Outputs (heuristic mode):**

| File | Issues found | Fix | Score / level | Auto-fix |
|---|---|---|---|---|
| `cleanish.py` | none | code unchanged | 100 / low | yes |
| `print_spam.py` | Code Quality (Low) | `print(` replaced with `logging.info(`, `import logging` added | 95 / low | yes |
| `flaky_try_except.py` | Reliability (High) | `except:` replaced with `except Exception as e:` plus a placeholder comment | 55 / medium | no |
| `mixed_issues.py` | Code Quality (Low), Reliability (High), Maintainability (Medium) | print and except rewritten; `TODO` left in place | 30 / high | no |

Fixes are small regex rewrites. The risk report lists one reason per deduction (for example "High severity issue detected.").

---

## 4) Reliability and safety rules

**Rule 1: severity deductions (High -40, Medium -20, Low -5).**
- Checks: each reported issue lowers the score by its severity.
- Why it matters: code with serious problems should get human review even if the fix looks tidy; two High issues alone push the score below 40.
- False positive: a trivially correct fix is still penalized because the original was bad, so a safe one-line fix of a High issue lands at 55 and is never auto-applied.
- False negative: severity comes from the analyzer, not from the fix. A missed issue costs nothing: `def f(path, cache=[])` with `except Exception: pass` produced no issues and scored 100 with auto-fix allowed.

**Rule 2: removed `return` (-30).**
- Checks: `"return"` appears in the original but not in the fixed code (substring check).
- Why it matters: dropping a return changes what the function gives back.
- False positive: the word can appear in a comment or string, and a legitimate refactor might remove returns on purpose.
- False negative: it only tests presence of the word anywhere. `def f(): return 1` rewritten to `def f(): x = 'return'` is not flagged (score 100), and removing one of several returns is not flagged.

**Rule 3: fixed code much shorter than original (-20 when under 50% of the lines).**
- Checks: line count of the fix against the original.
- Why it matters: a big shrink suggests the model deleted logic.
- False positive: deleting dead code or a long comment block is legitimate.
- False negative: a fix that rewrites logic at the same length passes.

**Rule 4 (added in this work): fix must still parse (-50, blocks auto-fix).**
- Checks: `ast.parse` succeeds on the fix when it succeeds on the original.
- Why it matters: a syntactically broken fix would otherwise score as low risk (a Low issue plus a broken fix scored 95 before).
- False positive: a snippet that is a valid fragment but not a valid module is only penalized if the original parsed and the fix did not.
- False negative: syntax only. A fix that parses but changes behavior is not caught.

---

## 5) Observed failure modes

Four real instances, all reproduced offline:

1. **Missed issue (false negative).** `def f(path, cache=[]): try: return open(path).read() except Exception: pass` returned no issues, score 100, auto-fix allowed. The analyzer only knows three patterns, so a mutable default argument and a swallowed exception are invisible. Auto-fix on "no issues" means the code is returned unchanged, but the 100 / low report overstates how safe the code is.
2. **Fix that doesn't fix.** On `flaky_try_except.py` the heuristic fix only rewrites `except:` to `except Exception as e:` and adds a placeholder comment. The error is still silently swallowed (`return None`) and `e` is unused. It scored 55 / medium, so it was correctly not auto-applied, but the fix itself is cosmetic.
3. **Unnecessary edit on `mixed_issues.py`.** The `TODO` issue is reported but the fixer has no rule for it, so it is left in place. The report says it found a Medium issue; the fix does nothing about it.
4. **False positive plus unsafe confidence (fixed).** The `footprint(x)` case below.

**Failure mode found and fixed: identifier corruption with unsafe confidence.**
- Snippet: `def f(x):\n    footprint(x)\n    return x\n` (heuristic mode).
- What went wrong: the print detector used `"print(" in code` and the fixer used `str.replace`, so `footprint(` was flagged and rewritten to `footlogging.info(`, an undefined name. The result still parsed, kept `return` and its length, so `assess_risk` scored it 95 / low and allowed auto-fix. It would raise `NameError` at runtime.
- Fix: both steps now use `\bprint\(` (`_PRINT_CALL` in `bughound_agent.py`). Guardrail placed in the agent workflow, since the false positive is the root cause; a general "undefined names" check in `assess_risk` would need symbol analysis. Regression tests are in `tests/test_agent_workflow.py`.
- Before: issue reported, code rewritten, 95 low, auto-fix True. After: no issue, code unchanged, 100 low. Sample files unchanged (cleanish 100, mixed_issues 30, print_spam 95).
- Still open: a literal `print(` inside a string or comment is still flagged and rewritten (needs tokenizing). Comments-only files with a `TODO` also report auto-fix True although nothing changes, and an empty file reports "No fix was produced" at score 0.

---

## 6) Heuristic vs Gemini comparison

**Gemini was not run live in this work, so there is no observed Gemini comparison.** What I can say from the code and stub runs:

- **Heuristics:** deterministic and consistent. They caught exactly the three patterns they encode (print, bare except, TODO) on every run, and missed everything else (see failure mode 1).
- **Expected Gemini differences (not observed):** the prompt asks for reliability, maintainability, correctness and readability issues, so it should find more than three pattern types. Its fixes should be freer rewrites than the regex substitutions, which raises over-editing risk; the size and `return` checks and the parse check exist for that case.
- **What I did test with stubs:** wrong-shape model output (`[{"foo":1}]`), a bad severity, an empty array, and a fix that doesn't parse. The agent now handles these by falling back or dropping items, and logs why. Before the change, wrong-shape output produced a placeholder issue (`Issue / Unknown`) and a score of 100.
- **To complete this section:** run `mixed_issues.py` once in Gemini mode and compare the trace (which now logs the raw model reply) with the table in section 3.
- **Risk scorer vs intuition (heuristic mode):** it matched my intuition on the four files. It disagreed on `footprint(x)` (95 / low for a broken fix) and on the mutable-default case (100 for risky code).

---

## 7) Human-in-the-loop decision

**Scenario:** a model-written fix changes a function's signature, for example renaming a function or adding, removing or reordering parameters. Callers elsewhere would break, but the fix parses, keeps its returns and keeps its length, so it can score as low risk today.

- **Trigger:** compare the `def` names and argument lists of the original and fixed code with `ast`. Any difference forces `should_autofix = False` and drops the score into the medium band at least.
- **Where:** `reliability/risk_assessor.py`, next to the parse check, because it is a property of the fix rather than of the analysis, and it works for both heuristic and Gemini fixes. The UI should only display the result.
- **Message:** "This fix changes a function signature (`load(path)` is now `load(path, mode)`). Other code may call it. Review before applying."
- Not implemented; the parse check is the closest existing guard.

---

## 8) Improvement idea

**Done in this work:** three small changes, each with a before/after below: strict validation of model output, a parse check in the risk assessor, and a word-boundary match for print calls.

**Next improvement (not built): find `print` calls with `ast` instead of regex.** The detector and fixer would walk the syntax tree for calls to the name `print`, so a `print(` inside a string or comment is never flagged or rewritten (`MSG = "use print( to debug"` is currently rewritten to `logging.info(`). It is a small change in `_heuristic_analyze` and `_heuristic_fix`. To measure it, run a set of snippets with `print(` in strings and comments plus real calls, and count false positives: currently at least 1 of the crafted cases, expected 0 after.


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

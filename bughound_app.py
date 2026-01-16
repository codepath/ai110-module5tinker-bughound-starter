import os
import difflib
import streamlit as st
from dotenv import load_dotenv

from bughound_agent import BugHoundAgent
from llm_client import GeminiClient, MockClient

# ----------------------------
# App setup
# ----------------------------
st.set_page_config(page_title="BugHound", page_icon="🐶", layout="wide")
st.title("🐶 BugHound")
st.caption("A tiny agent that analyzes code, proposes a fix, and runs simple reliability checks.")

# Load environment variables from .env if present
load_dotenv()

# ----------------------------
# Helpers
# ----------------------------
SAMPLE_SNIPPETS = {
    "print_spam.py": """def greet(name):
    print("Hello", name)
    print("Welcome!")
    return True
""",
    "flaky_try_except.py": """def load_data(path):
    try:
        data = open(path).read()
    except:
        return None
    return data
""",
    "mixed_issues.py": """# TODO: replace with real implementation
def compute(x, y):
    print("computing...")
    try:
        return x / y
    except:
        return 0
""",
    "cleanish.py": """import logging

def add(a, b):
    logging.info("Adding numbers")
    return a + b
""",
}


def render_diff(original: str, revised: str) -> str:
    """Return a unified diff string."""
    diff_lines = difflib.unified_diff(
        original.splitlines(),
        revised.splitlines(),
        fromfile="original",
        tofile="fixed",
        lineterm="",
    )
    return "\n".join(diff_lines)


def require_code_input(code: str) -> bool:
    if not code.strip():
        st.warning("Paste some code or load a sample snippet to begin.")
        return False
    return True


# ----------------------------
# Sidebar controls
# ----------------------------
st.sidebar.header("Settings")

mode = st.sidebar.selectbox(
    "Model mode",
    [
        "Heuristic only (no API)",
        "Gemini (requires API key)",
    ],
    help="Heuristic mode runs fully offline. Gemini mode calls the Gemini API for analysis and fix proposal.",
)

# [cite_start]UPDATED: Added a warning for free-tier users to manage expectations regarding API limits. [cite: 176, 192]
if mode == "Gemini (requires API key)":
    st.sidebar.warning("⚠️ Gemini Free Tier: You have a limit of ~20 requests. Use Heuristic mode for initial testing to save your quota.")

model_name = st.sidebar.selectbox(
    "Gemini model",
    ["gemini-2.5-flash", "gemini-2.5-pro"], # Reverting to existing version names from llm_client.py
    disabled=(mode != "Gemini (requires API key)"),
)

temperature = st.sidebar.slider(
    "Temperature",
    min_value=0.0,
    max_value=1.0,
    value=0.2,
    step=0.1,
    disabled=(mode != "Gemini (requires API key)"),
    help="Lower values tend to be more consistent. Higher values tend to be more creative.",
)

st.sidebar.divider()

sample_choice = st.sidebar.selectbox(
    "Load a sample snippet",
    ["(none)"] + list(SAMPLE_SNIPPETS.keys()),
)

show_debug = st.sidebar.checkbox("Show debug details", value=False)

# ----------------------------
# Choose client
# ----------------------------
client = None
client_status = ""

if mode == "Heuristic only (no API)":
    client = MockClient()
    client_status = "Using MockClient. No network calls."
else:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        client = None
        client_status = "Missing GEMINI_API_KEY. Add it to your .env file to use Gemini mode."
    else:
        client = GeminiClient(model_name=model_name, temperature=temperature)
        client_status = "Gemini client ready."

st.sidebar.info(client_status)

# ----------------------------
# Main input
# ----------------------------
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Input code")
    if sample_choice != "(none)":
        default_code = SAMPLE_SNIPPETS[sample_choice]
    else:
        default_code = st.session_state.get("code_input", "")

    code_input = st.text_area(
        "Paste a Python snippet",
        value=default_code,
        height=320,
        placeholder="Paste code here...",
        label_visibility="collapsed",
    )
    st.session_state["code_input"] = code_input

    run_button = st.button("Run BugHound", type="primary", use_container_width=True)

with col_right:
    st.subheader("Outputs")
    st.write("Run the workflow to see issues, a proposed fix, and a risk report.")

# ----------------------------
# Run workflow
# ----------------------------
if run_button:
    if not require_code_input(code_input):
        st.stop()

    if mode == "Gemini (requires API key)" and client is None:
        st.error("Gemini mode is selected, but no API key is available.")
        st.stop()

    agent = BugHoundAgent(client=client)

    with st.spinner("BugHound is sniffing around..."):
        result = agent.run(code_input)

    issues = result.get("issues", [])
    fixed_code = result.get("fixed_code", "")
    risk = result.get("risk", {})
    logs = result.get("logs", [])

    # Layout for results
    res_left, res_right = st.columns([1, 1])

    with res_left:
        st.subheader("Detected issues")
        if not issues:
            st.success("No issues detected by the current analyzer.")
        else:
            for i, issue in enumerate(issues, start=1):
                issue_type = issue.get("type", "Issue")
                severity = issue.get("severity", "Unknown")
                msg = issue.get("msg", "").strip()

                badge = f"{issue_type} | {severity}"
                st.markdown(f"**{i}. {badge}**")
                if msg:
                    st.write(msg)

    with res_right:
        st.subheader("Risk report")
        if not risk:
            st.info("No risk report was produced.")
        else:
            score = risk.get("score", None)
            level = risk.get("level", "unknown")
            should_autofix = risk.get("should_autofix", None)
            reasons = risk.get("reasons", [])

            top_cols = st.columns(3)
            with top_cols[0]:
                st.metric("Risk level", str(level).upper())
            with top_cols[1]:
                st.metric("Score", "-" if score is None else int(score))
            with top_cols[2]:
                st.metric("Auto-fix?", "-" if should_autofix is None else ("YES" if should_autofix else "NO"))

            if reasons:
                st.write("**Reasons:**")
                for r in reasons:
                    st.write(f"- {r}")

    st.divider()

    # [cite_start]UPDATED: Check if a fallback occurred due to API limits/errors and notify the user. [cite: 119, 128]
    if any("API Error" in log.get("message", "") for log in logs):
        st.warning("⚠️ API Request Failed: BugHound hit a limit or network error and used heuristic rules instead.")

    st.subheader("Proposed fix")
    if not fixed_code.strip():
        st.warning("No fix was produced. This can happen if the agent refused or had parsing errors.")
    else:
        fix_cols = st.columns([1, 1])

        with fix_cols[0]:
            st.text_area("Fixed code", value=fixed_code, height=320)

        with fix_cols[1]:
            diff_text = render_diff(code_input, fixed_code)
            st.text_area("Diff (unified)", value=diff_text, height=320)

    st.divider()

    st.subheader("Agent trace")
    if not logs:
        st.info("No trace logs were produced.")
    else:
        for entry in logs:
            step = entry.get("step", "LOG")
            message = entry.get("message", "")
            st.write(f"**{step}:** {message}")

    if show_debug:
        st.divider()
        st.subheader("Debug payload")
        st.json(result)

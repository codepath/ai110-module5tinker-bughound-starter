import streamlit as st
import time
import random
import re

# ==========================================
# 🧠 PART 1: The Agent Logic (Backend)
# ==========================================

class BugHoundAgent:
    """
    The 'Brain' of the operation. 
    """
    def __init__(self):
        self.logs = [] # Memory of the agent's thought process

    def log_thought(self, step, message):
        """Records the agent's reasoning steps."""
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] **{step}**: {message}"
        self.logs.append(entry)
        # Streamlit simulation of "thinking time"
        time.sleep(0.5) 

    def analyze_code(self, code_snippet):
        """
        Step 1: Retrieval & Analysis
        Currently uses Regex heuristics.
        """
        self.log_thought("PLAN", "Scanning code for syntax patterns and potential risks...")
        
        issues = []
        
        # 1. Check for print statements (Production cleanliness)
        if "print(" in code_snippet:
            issues.append({
                "type": "Code Quality",
                "severity": "Low",
                "msg": "Found 'print' statements. In production, use the 'logging' module."
            })
            self.log_thought("OBSERVATION", "Detected print statements.")

        # 2. Check for broad exceptions (Reliability)
        if re.search(r"except\s*:", code_snippet):
            issues.append({
                "type": "Reliability",
                "severity": "High",
                "msg": "Bare 'except:' clause detected. This hides errors. Specify the Exception type."
            })
            self.log_thought("CRITIQUE", "Found unsafe bare exception handling.")

        # 3. Check for TODOs (Completeness)
        if "TODO" in code_snippet:
            issues.append({
                "type": "Completeness",
                "severity": "Medium",
                "msg": "Unresolved 'TODO' comment found."
            })
        
        if not issues:
            self.log_thought("CONCLUSION", "No heuristic issues found. Code looks ostensibly clean.")
        
        return issues

    def generate_fix(self, code_snippet, issues):
        """
        Step 2: Action
        Generates a suggested fix.
        """
        self.log_thought("ACT", "Attempting to refactor code based on identified issues...")
        
        fixed_code = code_snippet
        
        # Simulation of fixing logic
        if any(i['msg'].startswith("Found 'print'") for i in issues):
            fixed_code = "# [BugHound] Replaced print with logging\nimport logging\n" + \
                         fixed_code.replace("print(", "logging.info(")
        
        if any(i['msg'].startswith("Bare 'except'") for i in issues):
            fixed_code = fixed_code.replace("except:", "except Exception as e: # [BugHound] Added specific catch")

        self.log_thought("REFLECT", "Refactoring complete. Ready for review.")
        return fixed_code

    def validate_fix(self, original_code, fixed_code):
        """
        Step 3: Verification (Guardrails)
        Ensures the fix didn't break everything.
        """
        self.log_thought("TEST", "Running simulation tests on the new code...")
        
        # Mock Validation Logic
        score = random.randint(80, 100)
        success = True
        
        if len(fixed_code) < len(original_code):
            self.log_thought("WARNING", "The fixed code is significantly shorter. Checking for data loss...")
            score -= 10
            
        return success, score

# ==========================================
# 🖥️ PART 2: The Streamlit UI (Frontend)
# ==========================================

st.set_page_config(page_title="BugHound 🪲", layout="wide")

st.title("🪲 BugHound: Agentic Debugger")
st.markdown("""
**Welcome to Lab 5.** This tool demonstrates an **Agentic Workflow**.
Instead of just giving an answer, BugHound will:
1. **Plan** its approach.
2. **Analyze** your code for specific patterns.
3. **Act** to generate a fix.
4. **Reflect** on the quality of the fix.
""")

# --- Sidebar Controls ---
st.sidebar.header("⚙️ Agent Settings")
model_choice = st.sidebar.selectbox("Select Model", ["Simulated Heuristics", "GPT-4o (Placeholder)", "Claude 3.5 (Placeholder)"])
auto_fix = st.sidebar.checkbox("Auto-apply fixes?", value=False)

# --- Main Input Area ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📝 Input Code")
    user_code = st.text_area("Paste Python code here:", height=300, value="""
def calculate_data(data):
    try:
        # TODO: Implement proper math
        result = data * 2
        print(f"Result is {result}")
        return result
    except:
        print("Something went wrong")
""")
    
    run_btn = st.button("🐕 Unleash the Hound", type="primary")

# --- Processing & Output ---
if run_btn:
    agent = BugHoundAgent()
    
    # 1. The Agent Loop Visualization
    with col2:
        st.subheader("🧠 Agent Reasoning")
        with st.status("BugHound is thinking...", expanded=True) as status:
            # Phase 1: Analyze
            issues = agent.analyze_code(user_code)
            
            # Phase 2: Fix (if issues exist)
            fixed_code = user_code
            if issues:
                fixed_code = agent.generate_fix(user_code, issues)
            
            # Phase 3: Validate
            valid, confidence = agent.validate_fix(user_code, fixed_code)
            
            # Update Status
            status.update(label="Analysis Complete!", state="complete", expanded=False)

        # Show the "Thought Log" (Explainability)
        with st.expander("View Internal Thought Log", expanded=False):
            for log in agent.logs:
                st.markdown(log)

    # 2. Results Display
    st.divider()
    
    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Issues Found", len(issues), delta_color="inverse")
    m2.metric("Confidence Score", f"{confidence}%")
    m3.metric("Status", "✅ Fixed" if valid else "⚠️ Review Needed")

    # Code Comparison
    st.subheader("🔍 Code Review")
    
    if not issues:
        st.success("No major issues found! Your code is squeaky clean. ✨")
    else:
        diff_col1, diff_col2 = st.columns(2)
        with diff_col1:
            st.markdown("**❌ Issues Detected**")
            for i in issues:
                st.error(f"**[{i['type']}]**: {i['msg']}")
        
        with diff_col2:
            st.markdown("**✅ Suggested Fix**")
            st.code(fixed_code, language="python")
            
            if st.button("Copy to Clipboard"):
                st.toast("Code copied! (Simulated)")

# --- Footer / Learning Context ---
st.divider()
st.info("""
Currently, `BugHoundAgent` uses simple `if/else` statements (Heuristics) to find bugs. 
**Your job is to replace the `analyze_code` and `generate_fix` methods with actual calls to an LLM API.**
Make the agent *actually* intelligent!
""")

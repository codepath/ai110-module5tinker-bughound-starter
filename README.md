# BugHound 🪲

**BugHound** is an "Agentic Debugger" application built with Streamlit. It demonstrates an agentic workflow where an AI agent plans, analyzes code, acts to generate fixes, and reflects on the results.

Currently, this is a **starter project** that uses simulated heuristics (regex and simple logic) to detect bugs. The goal of this project is to eventually replace the simulated logic with actual LLM API calls to make the agent truly intelligent.

## Features

- **Agent Reasoning Visualization**: Watch the agent "think" as it processes your code.
- **Heuristic Code Analysis**: Detects common issues like:
  - `print()` statements (suggests using `logging`).
  - Bare `except:` clauses (suggests catching specific exceptions).
  - `TODO` comments.
- **Automated Fixes**: Generates suggested refactorings for detected issues.
- **Interactive UI**: Paste your Python code and get instant feedback.

## Installation

1. **Clone the repository** (if you haven't already).
2. **Install dependencies**: Ensure you have Python installed, then run:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the application using Streamlit:

```bash
streamlit run bughound_app.py
```

The app will open in your default web browser.

## How it Works

The app is split into two parts:

1. **The Agent Logic (`BugHoundAgent` class)**:
   - `analyze_code`: Scans the input code for specific patterns.
   - `generate_fix`: Applies string replacements to fix identified issues.
   - `validate_fix`: Simulates a testing phase to ensure the fix is safe.

2. **The Streamlit UI**: Provides the interface for inputting code and viewing the agent's logs and results.

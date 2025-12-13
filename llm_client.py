import os
from typing import Optional


class MockClient:
    """
    Offline stand-in for an LLM client.
    This lets the app run without an API key.

    NOTE: It intentionally returns non-JSON-ish outputs so students can see
    how the agent falls back to heuristics in analyze(), and how propose_fix()
    may fall back too.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Very small, predictable behavior for demos.
        if "Return ONLY valid JSON" in system_prompt:
            # Purposely not JSON to force fallback unless students change behavior.
            return "I found some issues, but I'm not returning JSON right now."
        return "# MockClient: no rewrite available in offline mode.\n"


class GeminiClient:
    """
    Minimal Gemini API wrapper.

    Requirements:
    - google-generativeai installed
    - GEMINI_API_KEY set in environment (or loaded via python-dotenv)
    """

    def __init__(self, model_name: str = "gemini-1.5-flash", temperature: float = 0.2):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "Missing GEMINI_API_KEY. Create a .env file and set GEMINI_API_KEY=..."
            )

        # Import here so heuristic mode doesn't require the dependency at import time.
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.temperature = float(temperature)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Sends a single request to Gemini.

        We use a simple two-part prompt: system + user. If the model returns
        extra text (like markdown), downstream parsing utilities should handle it.
        """
        response = self.model.generate_content(
            [
                {"role": "system", "parts": [system_prompt]},
                {"role": "user", "parts": [user_prompt]},
            ],
            generation_config={"temperature": self.temperature},
        )

        # Defensive: response.text can be None in edge cases.
        return response.text or ""

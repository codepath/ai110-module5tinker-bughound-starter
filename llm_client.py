import os
from typing import Optional


class MockClient:
    """
    Offline stand-in for an LLM client.
    This lets the app run without an API key.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Very small, predictable behavior for demos.
        if "Return ONLY valid JSON" in system_prompt:
            # Purposely not JSON to force fallback unless students change behavior.
            return "I found some issues, but I'm not returning JSON right now."
        return "# MockClient: no rewrite available in offline mode.\n"


class GeminiClient:
    """
    Minimal Gemini API wrapper with added error resilience.

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

        UPDATED: Added try/except to handle rate limits and API errors gracefully.
        If an error occurs, it returns an empty string, triggering the agent's 
        heuristic fallback logic.
        """
        try:
            response = self.model.generate_content(
                [
                    {"role": "system", "parts": [system_prompt]},
                    {"role": "user", "parts": [user_prompt]},
                ],
                generation_config={"temperature": self.temperature},
            )

            # Defensive: response.text can be None or raise an error if blocked by filters.
            return response.text or ""
            
        except Exception as e:
            # Returning empty string allows the agent to detect the failure 
            # and switch to offline rules.
            return ""

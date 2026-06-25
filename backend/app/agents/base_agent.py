"""
MergeMind — Base Agent

Abstract base class for all AI review agents.
Handles Gemini API communication, prompt construction, and JSON output parsing.

All agents share:
  - A friendly, emoji-sprinkled tone
  - Concise bullet-style output
  - Structured JSON responses
  - Retry logic for parsing failures
"""

import json
import logging
import asyncio
from abc import ABC, abstractmethod
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from app.config import get_settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Shared Prompt Preamble
# ══════════════════════════════════════════════════════════════════════
# This preamble is prepended to every agent's system prompt.
# It establishes the tone, format, and output constraints.

AGENT_PREAMBLE = """You are a friendly, expert code reviewer working as part of the MergeMind review system. 🧠

Your tone should be:
• Friendly and helpful — you're a teammate, not a judge
• Use occasional emojis to keep things light 🎯
• Professional but approachable
• Concise — no essays, no walls of text

Output Format Rules:
• Return ONLY a valid JSON array of issue objects
• If no issues found, return an empty array: []
• Each issue must have exactly these fields:
  - "category": one of "bug", "security", "performance", "quality"
  - "severity": one of "critical", "warning", "info"
  - "title": short title, max 60 characters
  - "description": concise bullet-style explanation, 100-250 characters
• Do NOT wrap the JSON in markdown code blocks
• Do NOT include any text before or after the JSON array

Description Style:
• Start with "•" bullet point
• Be specific about the problem
• Mention the relevant code element (variable, function, etc.)
• Keep it actionable — suggest what to fix when possible

Good description example:
"• Possible null reference when `user.profile` is accessed without checking if user exists. Consider adding a null check."

Bad description example:
"This code has a potential issue where the user object might not exist and accessing the profile property could throw an error at runtime which would cause the application to crash."
"""


# ══════════════════════════════════════════════════════════════════════
# Strictness Instructions
# ══════════════════════════════════════════════════════════════════════
# These instructions are appended to the preamble based on the user's
# chosen strictness level.

STRICTNESS_INSTRUCTIONS = {
    "lenient": """
Review Strictness: LENIENT 🟢
• Focus on flagging actual bugs, syntax errors, security holes, and code execution breakages that will cause failures in production.
• Ignore minor style, naming consistency, missing comments, formatting, or subjective design quality concerns.
• Skip suggestion-level / info-level findings.
• Ensure any flagged issues are high confidence, but do not ignore syntax errors or actual program bugs.
• Set severity to "critical" for bugs causing crashes/compilation errors, and "warning" for other functional issues.
""",
    "moderate": """
Review Strictness: MODERATE 🟡
• Flag issues that a reasonable senior developer would consider worth addressing
• Balance thoroughness with pragmatism — don't nitpick, but don't miss real issues
• Include important style/quality issues only if they significantly hurt readability
• Use "info" severity sparingly — prefer "warning" for actionable items
""",
    "strict": """
Review Strictness: STRICT 🔴
• Be thorough — flag ALL potential issues, even minor style and quality concerns
• Better to over-report than under-report
• Include suggestions for improvement, not just problems
• Flag naming issues, missing comments, code structure improvements
• Use the full severity range: "info" for suggestions, "warning" for concerns, "critical" for serious issues
• If there's any doubt about code quality, flag it
""",
}


class BaseAgent(ABC):
    """
    Abstract base class for AI review agents.
    
    Subclasses must implement:
        - agent_name: A human-readable name for the agent
        - category: The issue category this agent produces
        - get_system_prompt(): Returns the domain-specific system prompt
    
    Usage:
        agent = CodeQualityAgent()
        issues = await agent.analyze(code_context_string, strictness="moderate")
    """

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name for this agent (e.g., 'Code Quality Agent')."""
        ...

    @property
    @abstractmethod
    def category(self) -> str:
        """Issue category this agent produces (e.g., 'quality', 'bug')."""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the domain-specific system prompt for this agent.
        The AGENT_PREAMBLE is automatically prepended.
        """
        ...

    async def analyze(self, code_context: str, strictness: str = "moderate") -> list[dict]:
        """
        Analyze code and return a list of issues.
        
        This method:
        1. Builds the full prompt (preamble + strictness + domain-specific + code)
        2. Calls the Gemini API
        3. Parses the JSON response
        4. Validates each issue has required fields
        
        Args:
            code_context: Formatted code context from context_builder
            strictness: Review strictness level ('lenient', 'moderate', 'strict')
            
        Returns:
            List of issue dictionaries, each with:
            {category, severity, title, description}
        """
        # Build prompt with strictness instruction
        strictness_text = STRICTNESS_INSTRUCTIONS.get(strictness, STRICTNESS_INSTRUCTIONS["moderate"])
        system_prompt = f"{AGENT_PREAMBLE}\n{strictness_text}\n\n{self.get_system_prompt()}"

        user_message = (
            f"Please review the following code changes and identify any "
            f"{self.category}-related issues:\n\n{code_context}"
        )

        max_retries = 5
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"🔍 {self.agent_name} starting analysis (strictness={strictness}, "
                    f"attempt={attempt + 1}/{max_retries})..."
                )

                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.3,
                        max_output_tokens=2000,
                    ),
                )

                raw_output = response.text.strip()

                # Parse and validate the JSON output
                issues = self._parse_response(raw_output)

                logger.info(
                    f"✅ {self.agent_name} found {len(issues)} issue(s)"
                )
                return issues

            except (ClientError, ServerError) as e:
                status_code = getattr(e, "status_code", None)
                if status_code in (429, 503) and attempt < max_retries - 1:
                    sleep_time = backoff * (2 ** attempt)
                    logger.warning(
                        f"⚠️ {self.agent_name} encountered {status_code} error: {str(e)}. "
                        f"Retrying in {sleep_time:.1f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error(f"❌ {self.agent_name} failed: {str(e)}")
                    raise e
            except Exception as e:
                logger.error(f"❌ {self.agent_name} failed: {str(e)}")
                raise e

        return []

    def _parse_response(self, raw_output: str) -> list[dict]:
        """
        Parse the agent's raw text output into a list of issue dicts.
        
        Handles common edge cases:
        - Output wrapped in markdown code blocks
        - Output with extra text before/after JSON
        - Invalid JSON (returns empty list)
        """
        # Strip markdown code block wrappers if present
        cleaned = raw_output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Try to find JSON array in the output
        # Sometimes models add text before/after the JSON
        start_idx = cleaned.find("[")
        end_idx = cleaned.rfind("]")

        if start_idx != -1 and end_idx != -1:
            cleaned = cleaned[start_idx : end_idx + 1]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(
                f"⚠️ {self.agent_name}: Could not parse JSON output. "
                f"Raw output: {raw_output[:200]}..."
            )
            return []

        # Ensure we have a list
        if not isinstance(parsed, list):
            parsed = [parsed]

        # Validate and normalize each issue
        validated_issues: list[dict] = []
        for item in parsed:
            if isinstance(item, dict) and "title" in item:
                issue = {
                    "category": item.get("category", self.category),
                    "severity": item.get("severity", "info"),
                    "title": str(item.get("title", ""))[:80],
                    "description": str(item.get("description", "")),
                }
                # Ensure description is within 100-250 chars
                if len(issue["description"]) > 300:
                    issue["description"] = issue["description"][:297] + "..."
                validated_issues.append(issue)

        return validated_issues

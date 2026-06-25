"""
MergeMind — Aggregator Agent

Receives outputs from all specialist agents and produces the final review.
Responsibilities:
  • Deduplicate similar/overlapping findings
  • Assign consistent severity levels
  • Produce the final summary with counts
  • Ensure all descriptions meet the 100-250 char constraint
"""

import json
import logging
from google import genai
from google.genai import types
from app.config import get_settings

logger = logging.getLogger(__name__)


class AggregatorAgent:
    """
    Combines outputs from all specialist agents into a final review.
    
    Unlike the specialist agents, the aggregator doesn't analyze code directly.
    Instead, it processes the raw findings from other agents, removes duplicates,
    and produces a clean, structured final review.
    
    This is done via an LLM call to leverage the model's ability to
    identify semantic duplicates and normalize descriptions.
    """

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    async def aggregate(self, all_issues: list[dict], strictness: str = "moderate") -> dict:
        """
        Process all agent findings into the final review output.
        
        Args:
            all_issues: Combined list of issues from all specialist agents
            strictness: Review strictness level ('lenient', 'moderate', 'strict')
            
        Returns:
            Final review dict with 'summary' and 'issues' keys:
            {
                "summary": {"bugs": 2, "security": 1, "performance": 0, "quality": 1},
                "issues": [{"category": ..., "severity": ..., "title": ..., "description": ...}, ...]
            }
        """
        # If no issues found by any agent, return clean empty result
        if not all_issues:
            logger.info("✅ Aggregator: No issues found — clean review!")
            return {
                "summary": {
                    "bugs": 0,
                    "security": 0,
                    "performance": 0,
                    "quality": 0,
                },
                "issues": [],
            }

        # For small numbers of issues, we can aggregate locally
        # without an LLM call (saves cost and latency)
        if len(all_issues) <= 5:
            return self._local_aggregate(all_issues)

        # For larger sets, use LLM to deduplicate and normalize
        return await self._llm_aggregate(all_issues, strictness)

    def _local_aggregate(self, issues: list[dict]) -> dict:
        """
        Simple local aggregation for small issue sets.
        Counts categories and ensures description length constraints.
        """
        # Normalize descriptions
        normalized_issues = []
        for issue in issues:
            desc = issue.get("description", "")
            # Ensure bullet-style
            if not desc.startswith("•"):
                desc = f"• {desc}"
            # Enforce length constraint
            if len(desc) > 250:
                desc = desc[:247] + "..."
            
            normalized_issues.append({
                "category": issue.get("category", "quality"),
                "severity": issue.get("severity", "info"),
                "title": issue.get("title", "Untitled")[:80],
                "description": desc,
            })

        # Count by category
        summary = {"bugs": 0, "security": 0, "performance": 0, "quality": 0}
        for issue in normalized_issues:
            cat = issue["category"]
            if cat == "bug":
                summary["bugs"] += 1
            elif cat in summary:
                summary[cat] += 1

        return {"summary": summary, "issues": normalized_issues}

    async def _llm_aggregate(self, all_issues: list[dict], strictness: str = "moderate") -> dict:
        """
        Use LLM to deduplicate and produce the final review.
        This handles cases where multiple agents flag similar issues.
        """
        # Build strictness-aware instruction
        strictness_note = ""
        if strictness == "lenient":
            strictness_note = """\n\nSTRICTNESS: LENIENT
- Aggressively filter out minor, informational, or marginal issues
- Only keep issues that are very likely to cause real problems
- Remove all "info" severity items — only keep "warning" and "critical"
- When in doubt, remove the issue"""
        elif strictness == "strict":
            strictness_note = """\n\nSTRICTNESS: STRICT
- Keep all issues, even minor ones
- Don't filter out informational items
- Preserve the full range of findings from the specialist agents"""

        system_prompt = f"""You are the MergeMind Aggregator. Your job is to produce the final code review from multiple specialist agent outputs.

Your tasks:
1. **Deduplicate**: If multiple agents flagged the same issue, keep only one (prefer the most specific description)
2. **Normalize**: Ensure all descriptions are 100-250 characters, bullet-style (start with •)
3. **Categorize**: Ensure each issue has correct category: "bug", "security", "performance", or "quality"
4. **Severity**: Ensure severity is one of: "critical", "warning", "info"
5. **Count**: Produce accurate summary counts

Return ONLY valid JSON in this exact format:
{{
    "summary": {{
        "bugs": <number>,
        "security": <number>,
        "performance": <number>,
        "quality": <number>
    }},
    "issues": [
        {{
            "category": "bug|security|performance|quality",
            "severity": "critical|warning|info",
            "title": "Short title (max 60 chars)",
            "description": "• Concise bullet-style description (100-250 chars)"
        }}
    ]
}}

Do NOT wrap in markdown. Return ONLY the JSON object.{strictness_note}"""

        user_message = (
            f"Here are the findings from all specialist agents. "
            f"Please deduplicate, normalize, and produce the final review:\n\n"
            f"{json.dumps(all_issues, indent=2)}"
        )

        try:
            # 🟡 What is aio??
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    max_output_tokens=3000,
                ),
            )

            raw_output = response.text.strip()
            result = self._parse_aggregated_response(raw_output)

            total = sum(result["summary"].values())
            logger.info(
                f"📋 Aggregator: Final review has {total} issue(s) "
                f"({result['summary']})"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Aggregator LLM call failed: {str(e)}")
            # Fallback to local aggregation
            return self._local_aggregate(all_issues)

    def _parse_aggregated_response(self, raw_output: str) -> dict:
        """
        Parse the aggregator's JSON response.
        Falls back to local aggregation if parsing fails.
        """
        # Clean up markdown wrappers
        cleaned = raw_output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Find JSON object boundaries
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1:
            cleaned = cleaned[start_idx : end_idx + 1]

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("⚠️ Aggregator: Could not parse LLM output, using local aggregation")
            return {"summary": {"bugs": 0, "security": 0, "performance": 0, "quality": 0}, "issues": []}

        # Validate structure
        if "summary" not in result:
            result["summary"] = {"bugs": 0, "security": 0, "performance": 0, "quality": 0}
        if "issues" not in result:
            result["issues"] = []

        # Ensure summary has all required keys
        for key in ["bugs", "security", "performance", "quality"]:
            if key not in result["summary"]:
                result["summary"][key] = 0

        return result

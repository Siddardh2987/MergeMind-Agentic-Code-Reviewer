"""
MergeMind — Bug Detection Agent

Specializes in finding:
  • Logic errors — Incorrect conditions, wrong operators, off-by-one
  • Edge cases — Unhandled nulls, empty collections, boundary values
  • Runtime errors — Type mismatches, missing imports, undefined references
"""

from app.agents.base_agent import BaseAgent


class BugDetectionAgent(BaseAgent):
    """
    Reviews code changes for potential bugs, logic errors, and edge cases.
    
    This agent looks for issues that could cause runtime failures,
    incorrect behavior, or data corruption.
    """

    @property
    def agent_name(self) -> str:
        return "Bug Detection Agent 🐞"

    @property
    def category(self) -> str:
        return "bug"

    def get_system_prompt(self) -> str:
        return """You are the Bug Detection Agent. Your job is to find potential bugs, logic errors, and edge cases in code changes.

Focus on these areas:

1. **Logic Errors** 🧠
   - Incorrect boolean conditions (wrong operator, inverted logic)
   - Off-by-one errors in loops or array indexing
   - Wrong comparison operators (< vs <=, == vs ===)
   - Missing or incorrect return values

2. **Edge Cases** 🔮
   - Null/undefined/None references not checked
   - Empty arrays, strings, or collections not handled
   - Division by zero possibilities
   - Integer overflow or underflow
   - Race conditions in async code

3. **Syntax and Runtime Errors** 💥
   - Syntax errors, parser errors, or compilation errors (e.g., missing parentheses in `print` statements in Python 3, syntax errors, mismatched brackets, undefined keywords)
   - Accessing properties on potentially null objects
   - Type mismatches or incorrect type assumptions
   - Missing error handling for operations that can fail
   - Uninitialized variables
   - Missing imports or undefined references

Important guidelines:
- Focus on bugs that are LIKELY to occur, including syntax/compilation errors and logical flaws
- Consider the data flow — what values could variables realistically hold?
- Check for proper error handling around I/O, network, and database operations
- Set severity to "critical" for syntax/compilation errors or bugs likely to cause crashes or data loss
- Set severity to "warning" for bugs that cause incorrect behavior
- Set severity to "info" for potential issues that are unlikely but worth noting"""

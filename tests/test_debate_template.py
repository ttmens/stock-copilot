"""Tests for debate prompt template refactoring."""

from src.agents.debate import (
    DEBATE_PROMPT_CAPITAL,
    DEBATE_PROMPT_FUNDAMENTAL,
    DEBATE_PROMPT_TECHNICAL,
    _get_debate_prompt,
)


class TestDebatePromptTemplate:
    """Test debate prompt parameterization."""

    def test_get_debate_prompt_technical(self):
        """_get_debate_prompt('技术面') should produce technical prompt."""
        prompt = _get_debate_prompt("技术面")
        assert "技术面" in prompt
        assert "bullish" in prompt
        assert "bearish" in prompt

    def test_get_debate_prompt_capital(self):
        """_get_debate_prompt('资金面') should produce capital prompt."""
        prompt = _get_debate_prompt("资金面")
        assert "资金面" in prompt

    def test_get_debate_prompt_fundamental(self):
        """_get_debate_prompt('基本面') should produce fundamental prompt."""
        prompt = _get_debate_prompt("基本面")
        assert "基本面" in prompt

    def test_backward_compat_aliases(self):
        """Legacy constants should still work."""
        assert "技术面" in DEBATE_PROMPT_TECHNICAL
        assert "资金面" in DEBATE_PROMPT_CAPITAL
        assert "基本面" in DEBATE_PROMPT_FUNDAMENTAL

    def test_prompts_share_structure(self):
        """All prompts should have the same JSON output format."""
        for focus in ["技术面", "资金面", "基本面"]:
            prompt = _get_debate_prompt(focus)
            assert '"sentiment"' in prompt
            assert '"summary"' in prompt
            assert '"focus_points"' in prompt
            assert '"risk_points"' in prompt
            assert '"agree_with_others"' in prompt

    def test_prompt_has_code_name_placeholders(self):
        """Prompts should contain {code} and {name} for formatting."""
        prompt = _get_debate_prompt("技术面")
        assert "{code}" in prompt
        assert "{name}" in prompt

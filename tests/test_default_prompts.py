import pytest
from book_translator.default_prompts import PROMPTS, get_prompt, TRANSLATION_PROMPT, TERM_DISCOVERY_PROMPT


class TestDefaultPrompts:
    def test_all_four_prompts_exist(self):
        required = ['translation', 'term_discovery', 'proofreading', 'global_proofreading']
        for name in required:
            assert name in PROMPTS, f"Missing prompt: {name}"

    def test_prompts_are_non_trivial(self):
        for name, content in PROMPTS.items():
            assert len(content) > 100, f"Prompt '{name}' is too short: {len(content)} chars"

    def test_translation_has_required_placeholders(self):
        assert '{text}' in TRANSLATION_PROMPT
        assert '{glossary}' in TRANSLATION_PROMPT
        assert '{style_guide}' in TRANSLATION_PROMPT
        assert '{previous_context}' in TRANSLATION_PROMPT

    def test_term_discovery_has_required_placeholders(self):
        assert '{text}' in TERM_DISCOVERY_PROMPT
        assert '{glossary}' in TERM_DISCOVERY_PROMPT

    def test_get_prompt_returns_content(self):
        result = get_prompt('translation')
        assert result == PROMPTS['translation']
        assert len(result) > 100

    def test_get_prompt_all_names_work(self):
        for name in ['translation', 'term_discovery', 'proofreading', 'global_proofreading']:
            result = get_prompt(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_prompt_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown prompt"):
            get_prompt('nonexistent')

    def test_get_prompt_error_lists_available(self):
        try:
            get_prompt('bad_name')
        except KeyError as e:
            assert 'translation' in str(e)

    def test_prompts_dict_has_four_entries(self):
        assert len(PROMPTS) == 4

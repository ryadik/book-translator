import pytest
from book_translator.default_prompts import PROMPTS


class TestDefaultPrompts:
    def test_all_four_prompts_exist(self):
        required = ['translation', 'term_discovery', 'proofreading', 'global_proofreading']
        for name in required:
            assert name in PROMPTS, f"Missing prompt: {name}"

    def test_prompts_are_non_trivial(self):
        for name, content in PROMPTS.items():
            assert len(content) > 100, f"Prompt '{name}' is too short: {len(content)} chars"

    def test_translation_has_required_placeholders(self):
        t = PROMPTS['translation']
        assert '{text}' in t
        assert '{glossary}' in t
        assert '{style_guide}' in t
        assert '{previous_context}' in t

    def test_term_discovery_has_required_placeholders(self):
        t = PROMPTS['term_discovery']
        assert '{text}' in t
        assert '{glossary}' in t

    def test_prompts_dict_has_four_entries(self):
        assert len(PROMPTS) == 4

"""
Language-specific data for book-translator.

Centralizes all language-dependent information:
- Language names (for prompt parametrization)
- Typography rules per target language (extracted from prompt ANCHOR D)
"""

# ISO 639-1 → language name in English (used in LLM prompts)
LANGUAGE_NAMES: dict[str, str] = {
    'ja': 'Japanese',
    'en': 'English',
    'zh': 'Chinese',
    'ko': 'Korean',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'pt': 'Portuguese',
    'it': 'Italian',
    'ar': 'Arabic',
    'ru': 'Russian',
}

# Target-language-specific typography rules.
# These are injected into translation/proofreading prompts via {typography_rules}.
# Currently only Russian is defined — add other target languages here as needed.
TYPOGRAPHY_RULES: dict[str, str] = {
    'ru': r"""### [ANCHOR D: BINARY TEXT PHYSICS & TYPOGRAPHY]

**CRITICAL ALGORITHM.** The text always exists in one of two states:
- State [SOUND]: Text spoken by a character.
- State [SILENCE]: Text narrated by the author.

Segment every sentence. Determine what is spoken and what is authorial explanation.

#### TRIGGER OPERATOR `─` (U+2500)

The symbol `─` (U+2500) is the sole separator between states [SOUND] and [SILENCE]. Inside paragraphs and sentences – AS WELL.
*   Place `─` **every time** the source of the text changes within a paragraph (speech started, speech interrupted by author, speech resumed).
*   Every new speech segment must launch with `─`, in a new paragraph.
*   *Rule:* If a Character speaks, and then the Author narrates – `─` must stand between them.

#### INTERRUPTION LOGIC

If speech cuts off mid-word or on a pause:
*   Mark interrupted phrases, sudden cut-offs, or trailing offs with an ellipsis `…`.
*   If a character's speech is broken into multiple paragraphs, each paragraph (except the first) requires starting with `─ … [text]`.
*   **Speech Cut-off:** Marked by an ellipsis `…`; continuation of the interrupted phrase after a pause/remark always starts with `─ …`.
    *   *Example:* `─ Я не… ─ он запнулся. ─ …не знаю.`

#### STATE [SOUND] (Speech Rules)

*   Every new speech segment must launch with `─`, in a new paragraph.
*   **Quotation Marks:** Strictly forbidden for framing speech.
*   **Internal Objects:** Thoughts/inscriptions inside speech are highlighted with `«...»`.
*   **Internal Dash:** Use `–` (En-dash) **only** for pauses within a ***continuous*** flow of speech by one character.
    *   *Prohibition:* Never use `–` or `—` to separate author's words.

#### FORMATTING STANDARDS (Special Symbols)

*   **Thoughts, Quotes, Inscriptions, and Titles:** Strictly guillemets (chevrons) `«...»`. Nested – `«„..."»`.
*   **Internal Dash:** If it is not a boundary between Sound and Silence – use **ONLY** the en-dash (`–`).
    *   *Rule:* The em-dash (`—`) is forbidden everywhere.
*   **Indirect Speech (Fallback):** If unsure whether it is direct speech or a thought — use indirect speech (author's text) without quotation marks and without operators.

#### NON-STANDARD COMMS (Special Formats)

If the source contains **exotic communication** (telepathy, chat messages, AI voice, system notifications) highlighted by the author with **special graphic markers** (italics without quotes; brackets `[]`, `{}`, `<>`; etc.), then:
*   **Preserve Markers:** DO NOT CHANGE brackets or styles to dashes/quotes. Keep the framing as in the original.
*   **No Attribution:** DO NOT ADD quotation marks to such structures if they were not in the original, and do not use the speech operator `─` (since this is not spoken aloud).
*   **Translate Content:** Text inside markers is translated into {target_lang_name}.

#### CONTROL LOGIC

Before placing ANY dash, check the State on the Left and Right:

1. [SOUND]   <-> [SILENCE] : Use `─` (Operator). (Boundary switch).
2. [SILENCE] <-> [SOUND]   : Use `─` (Operator). (Boundary switch).
3. [SOUND]   <-> [SOUND]   : Use `–` (En-dash). (Internal pause in speech).
4. [SILENCE] <-> [SILENCE] : Use `–` (En-dash). (Internal pause in narration).

*Avoid the construction `, –` for internal pauses. Rephrase the sentence if necessary to use only the En-dash (`–`) without a preceding comma, or use alternative punctuation.*""",
}


def get_language_name(code: str) -> str:
    """Get human-readable language name for an ISO 639-1 code.

    Returns the code itself if not found in the mapping.
    """
    return LANGUAGE_NAMES.get(code, code)


def get_typography_rules(target_lang: str) -> str:
    """Get typography rules for the target language.

    Returns empty string if no rules defined for the given language.
    """
    return TYPOGRAPHY_RULES.get(target_lang, '')

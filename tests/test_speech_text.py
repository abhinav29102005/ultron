"""
Tests for utils/speech_text.py.

Bug this covers: every response was spoken verbatim. That was harmless while
skills answered in one sentence, but a researched answer carries "[1]" markers
and a trailing list of source URLs, and the synthesiser reads those aloud --
so the actual answer arrives buried in a minute of punctuation and hostnames.
"""

from __future__ import annotations

from utils.speech_text import (
    MAX_SPOKEN_CHARS,
    shorten_for_speech,
    spoken_form,
    strip_for_speech,
)


class TestStripping:
    def test_citation_markers_are_removed(self):
        assert strip_for_speech("Rust is memory safe [1][2].") == "Rust is memory safe."

    def test_grouped_citation_markers_are_removed(self):
        assert strip_for_speech("It shipped in 2015 [1, 2].") == "It shipped in 2015."

    def test_a_trailing_sources_block_is_removed(self):
        text = (
            "The release landed in June.\n"
            "\n"
            "Sources:\n"
            "1. Release notes - https://example.com/notes\n"
            "2. Blog - https://example.org/post\n"
        )
        assert strip_for_speech(text) == "The release landed in June."

    def test_inline_urls_are_removed(self):
        assert strip_for_speech("See https://example.com for details.") == (
            "See for details."
        )

    def test_markdown_emphasis_is_removed(self):
        assert strip_for_speech("**Yes** — see `main.py`") == "Yes — see main.py"

    def test_ordinary_text_is_left_alone(self):
        assert strip_for_speech("Chrome opened successfully.") == (
            "Chrome opened successfully."
        )


class TestShortening:
    def test_short_text_is_untouched(self):
        assert shorten_for_speech("All good.") == "All good."

    def test_long_text_is_cut_on_a_sentence_boundary(self):
        text = " ".join(f"Sentence number {i} goes here." for i in range(60))
        spoken = shorten_for_speech(text)

        assert len(spoken) < len(text)
        assert "The rest is on screen." in spoken
        # The cut must not land mid-sentence.
        body = spoken.replace(" The rest is on screen.", "")
        assert body.endswith(".")

    def test_a_single_over_long_sentence_is_kept_whole(self):
        """Clipping mid-word is worse than speaking slightly too long."""
        text = "word " * 200
        spoken = shorten_for_speech(text.strip())
        assert "word word" in spoken


class TestSpokenForm:
    def test_an_explicit_spoken_attribute_wins(self):
        class Result:
            spoken = "Three sources agree it shipped in June."

        out = spoken_form(Result(), "The release landed in June [1][2][3].\n\nSources:\n1. x")
        assert out == "Three sources agree it shipped in June."

    def test_a_spoken_method_is_called(self):
        """DeepResearchSkill's result computes its spoken form rather than
        storing it, so both shapes have to be accepted."""

        class Result:
            def spoken(self):
                return "Mars is cold. I read 3 sources for that."

        assert spoken_form(Result(), "Mars is cold [1].\n\nSources:\n1. x") == (
            "Mars is cold. I read 3 sources for that."
        )

    def test_an_explicit_spoken_form_is_still_length_budgeted(self):
        """Observed live: the research skill's spoken() returned a clean but
        600-character paragraph, which is a minute of speech the user cannot
        interrupt. Dropping citations is the skill's job; length is ours."""

        class Result:
            def spoken(self):
                return " ".join(f"Finding number {i} was confirmed." for i in range(80))

        spoken = spoken_form(Result(), "displayed")

        assert len(spoken) <= MAX_SPOKEN_CHARS + 40
        assert "The rest is on screen." in spoken

    def test_a_raising_spoken_method_falls_back_instead_of_losing_the_answer(self):
        class Result:
            def spoken(self):
                raise RuntimeError("boom")

        assert spoken_form(Result(), "Mars is cold [1].") == "Mars is cold."

    def test_a_blank_spoken_attribute_is_ignored(self):
        class Result:
            spoken = "   "

        assert spoken_form(Result(), "Chrome opened successfully.") == (
            "Chrome opened successfully."
        )

    def test_plain_string_results_still_work(self):
        """Most skills return a bare string and know nothing about this."""
        assert spoken_form("Chrome opened successfully.", "Chrome opened successfully.") == (
            "Chrome opened successfully."
        )

    def test_a_cited_answer_is_cleaned_for_the_voice(self):
        displayed = (
            "Python 3.13 removed the GIL behind a build flag [1]. "
            "It is not the default [2].\n"
            "\n"
            "Sources:\n"
            "1. PEP 703 - https://peps.python.org/pep-0703/\n"
        )
        spoken = spoken_form(None, displayed)

        assert "[1]" not in spoken
        assert "https" not in spoken
        assert "Sources" not in spoken
        assert "removed the GIL" in spoken

    def test_a_link_only_answer_still_says_something(self):
        """Silence would look like the request was ignored."""
        assert spoken_form(None, "https://example.com") == (
            "I've put what I found on screen."
        )

    def test_the_spoken_form_respects_the_length_budget(self):
        displayed = " ".join(f"Finding number {i} was confirmed." for i in range(80))
        spoken = spoken_form(None, displayed)
        # Allow for the appended pointer sentence.
        assert len(spoken) <= MAX_SPOKEN_CHARS + 40

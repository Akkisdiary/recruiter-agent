# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Recruiter Agent — a CLI tool that enhances LaTeX resumes against job descriptions using a LangGraph agent.

## Commands

```bash
uv sync                                    # Install dependencies
uv run ra --help                           # Show CLI usage (ra is short for recruiter-agent)
uv run ra resume.tex --jd-url "https://..."                    # Enhance via JD URL
uv run ra resume.tex --jd-file jd.txt                          # Enhance via JD text file
uv run ra resume.tex --jd-file jd.txt --no-interactive -v      # Non-interactive, verbose
uv run ra resume.tex --jd-file jd.txt --provider anthropic     # Use Anthropic instead of Google
```

Requires a `.env` file (gitignored) with API keys depending on provider:

- `GOOGLE_API_KEY` — default provider (`--provider google`, uses Gemini 2.5 Flash)
- `ANTHROPIC_API_KEY` — for `--provider anthropic`
- `OPENAI_API_KEY` — for `--provider openai`

No tests exist yet. No CI/CD configured.

## Architecture

The app is a LangGraph `StateGraph` with 8 nodes and a review loop, orchestrated from `agent/graph.py`:

```
parse_resume → scrape_jd → score_before → ask_clarifications → enhance_resume → score_after → review_changes
                                                                     ^                              |
                                                                     |     (user gives feedback)     |
                                                                     +-------------------------------+
                                                                                    |
                                                                              (user accepts)
                                                                                    ↓
                                                                              write_output
```

The conditional edge at `review_changes` is controlled by `_should_revise()` in `graph.py` — routes back to `enhance_resume` if `revision_feedback` is set, otherwise to `write_output`.

- **State** (`agent/state.py`): A `TypedDict` (with `total=False`) passed through the graph — holds parsed LaTeX, JD analysis, scores, enhanced output, and review loop fields (`revision_feedback`, `revision_count`).
- **Nodes** (`agent/nodes.py`): Each node reads state, does work (LLM call, file I/O, user prompt), and returns a partial state update. `enhance_resume_node` handles both initial enhancement (`ENHANCEMENT_PROMPT`) and revision passes (`REVISION_PROMPT`) based on `revision_count`. `review_changes_node` generates an LLM-powered change summary and prompts the user to accept or give feedback.
- **Prompts** (`agent/prompts.py`): `SYSTEM_PROMPT` (shared across all LLM calls), `JD_ANALYSIS_PROMPT`, `SCORING_PROMPT`, `CLARIFICATION_PROMPT`, `ENHANCEMENT_PROMPT`, `REVISION_PROMPT`, `CHANGE_SUMMARY_PROMPT`. The system prompt and scoring prompt emphasize recognizing transferable skills across domains rather than demanding exact keyword matches.
- **Schemas** (`models/schemas.py`): Pydantic models used as structured output targets — `JDAnalysis`, `ATSScore`, `ClarificationQuestion` (with `example_answer` field), `ClarificationRequest`, `EnhancedSections`, etc. All LLM calls use `.with_structured_output()`.
- **LaTeX handling** (`tools/latex.py`): Regex-based section splitting + `pylatexenc` for validation. The LLM only modifies section content — preamble, postamble, and `__header__` section are preserved untouched. Includes `escape_special_chars()`, `format_latex()`, and `validate_latex()`.
- **Scraping** (`tools/scraper.py`): `httpx` + `trafilatura` (primary) / `beautifulsoup4` (fallback) for extracting JD text from URLs. Falls back to manual paste if scraping fails.
- **Config** (`config.py`): LLM provider factory — returns `ChatAnthropic`, `ChatOpenAI`, or `ChatGoogleGenerativeAI` based on `--provider` flag. Default models: `claude-sonnet-4-20250514`, `gpt-4o`, `gemini-2.5-flash`.

The CLI (`cli.py`) uses Typer. Entry point is `recruiter-agent = recruiter_agent.cli:app` in pyproject.toml. `--no-interactive` skips both clarification questions and the review loop.

## Style Guidelines

- Respond in simple, easy-to-understand language. Keep answers short without irrelevant details.
- Avoid marketing language: do not use adjectives like "powerful", "built-in", "complete", "out-of-the-box", "hands-on", "essential", "production-ready", "makes it easy". Do not use phrases like "Check out", "Learn more", "Explore", "your needs", "choose the right...solution", "without changing your code", "automatically handles".
- Write for engineers — get into specifics and nuts-and-bolts details, not high-level benefit statements.
- Keep structure simple. Avoid deeply nested bullet points. Use emojis sparingly.

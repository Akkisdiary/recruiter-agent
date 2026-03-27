# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Recruiter Agent — a CLI tool that enhances LaTeX resumes against job descriptions using a LangGraph agent. Part of the Passionsfruit organization.

## Commands

```bash
uv sync                                    # Install dependencies
uv run recruiter-agent --help              # Show CLI usage
uv run recruiter-agent resume.tex --jd-url "https://..."                    # Enhance via JD URL
uv run recruiter-agent resume.tex --jd-file jd.txt                         # Enhance via JD text file
uv run recruiter-agent resume.tex --jd-file jd.txt --no-interactive -v     # Non-interactive, verbose
uv run recruiter-agent resume.tex --jd-file jd.txt --provider anthropic    # Use Anthropic instead of Google
```

Requires a `.env` file (gitignored) with API keys depending on provider:

- `GOOGLE_API_KEY` — default provider (`--provider google`, uses Gemini 2.5 Flash)
- `ANTHROPIC_API_KEY` — for `--provider anthropic`
- `OPENAI_API_KEY` — for `--provider openai`

## Architecture

The app is a LangGraph `StateGraph` with 7 sequential nodes, orchestrated from `agent/graph.py`:

```
parse_resume → scrape_jd → score_before → ask_clarifications → enhance_resume → score_after → write_output
```

- **State** (`agent/state.py`): A `TypedDict` passed through the graph — holds parsed LaTeX, JD analysis, scores, and enhanced output.
- **Nodes** (`agent/nodes.py`): Each node is a function that reads state, does work (LLM call, file I/O, user prompt), and returns a partial state update.
- **LaTeX handling** (`tools/latex.py`): Regex-based section splitting + `pylatexenc` for validation. The LLM only modifies section content — preamble, postamble, and header are preserved untouched. Includes `escape_special_chars()`, `format_latex()`, and `validate_latex()`.
- **Scraping** (`tools/scraper.py`): `httpx` + `trafilatura` (primary) / `beautifulsoup4` (fallback) for extracting JD text from URLs. Falls back to manual paste if scraping fails.
- **Schemas** (`models/schemas.py`): Pydantic models used as structured output targets for LLM calls (`JDAnalysis`, `ATSScore`, `EnhancedSections`, etc.).
- **Config** (`config.py`): LLM provider factory — returns `ChatAnthropic`, `ChatOpenAI`, or `ChatGoogleGenerativeAI` based on `--provider` flag.

The CLI (`cli.py`) uses Typer. Entry point is `recruiter-agent = recruiter_agent.cli:app` in pyproject.toml. Loads `.env` automatically via `python-dotenv`.

## Style Guidelines

- Respond in simple, easy-to-understand language. Keep answers short without irrelevant details.
- Avoid marketing language: do not use adjectives like "powerful", "built-in", "complete", "out-of-the-box", "hands-on", "essential", "production-ready", "makes it easy". Do not use phrases like "Check out", "Learn more", "Explore", "your needs", "choose the right...solution", "without changing your code", "automatically handles".
- Write for engineers — get into specifics and nuts-and-bolts details, not high-level benefit statements.
- Keep structure simple. Avoid deeply nested bullet points. Use emojis sparingly.

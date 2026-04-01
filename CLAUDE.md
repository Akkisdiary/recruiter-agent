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

Two-agent architecture with persistent message history, orchestrated as a single LangGraph `StateGraph` in `agent/graph.py`:

```
parse_resume → scrape_jd → score_before → ask_clarifications
  → recruiter_instruct → latex_expert_enhance → score_after → review_changes
         ^                                                         |
         |                                                         |
    recruiter_revise_instruct ←──────── (user feedback) ───────────+
                                                                   |
                                                             (user accepts)
                                                                   ↓
                                                             write_output
```

### Sub-agents

**Recruiter Agent** (strategist) — analyzes the JD, scores the resume, asks clarifying questions, and produces an `EnhancementPlan` with specific rewriting instructions. Has access to JD keywords and resume content. Its message history accumulates across nodes (`recruiter_messages` in state) so each step sees prior context.

**LaTeX Expert Agent** (writer) — receives the recruiter's `EnhancementPlan` and rewrites resume sections. Never sees raw JD keywords — only the recruiter's instructions. This prevents keyword stuffing structurally. Has its own message history (`writer_messages`).

The revision loop goes through the recruiter: `review_changes → recruiter_revise_instruct → latex_expert_enhance → score_after → review_changes`. The recruiter mediates every revision.

### Key components

- **State** (`agent/state.py`): `TypedDict` with `total=False`. Includes per-agent message histories using `Annotated[list[BaseMessage], add_messages]` — the `add_messages` reducer appends new messages rather than replacing.
- **Nodes** (`agent/nodes.py`): `score_before_node` seeds `recruiter_messages` with full context. `ask_clarifications_node` and `recruiter_instruct_node` append to it. `latex_expert_enhance_node` maintains separate `writer_messages`. `_format_plan_for_writer()` converts `EnhancementPlan` to readable prose.
- **Prompts** (`agent/prompts.py`): Split into recruiter prompts (`RECRUITER_SYSTEM_PROMPT`, `RECRUITER_INSTRUCTION_PROMPT`, `RECRUITER_REVISION_PROMPT`) and writer prompts (`WRITER_SYSTEM_PROMPT`, `WRITER_ENHANCE_PROMPT`, `WRITER_REVISION_PROMPT`). Shared: `JD_ANALYSIS_PROMPT`, `SCORING_PROMPT`, `CLARIFICATION_PROMPT`, `CHANGE_SUMMARY_PROMPT`.
- **Schemas** (`models/schemas.py`): `EnhancementPlan` (with `SectionInstruction` and `BulletInstruction`) is the contract between recruiter and writer. Other models: `JDAnalysis`, `ATSScore`, `ClarificationQuestion`, `EnhancedSections`.
- **LaTeX handling** (`tools/latex.py`): Regex-based section splitting + `pylatexenc` for validation. The `__header__` section is never sent to the LLM.
- **Scraping** (`tools/scraper.py`): `httpx` + `trafilatura` (primary) / `beautifulsoup4` (fallback). Falls back to manual paste if scraping fails.
- **Config** (`config.py`): LLM provider factory. Default models: `claude-sonnet-4-20250514`, `gpt-4o`, `gemini-2.5-flash`.

The CLI (`cli.py`) uses Typer. Entry points: `recruiter-agent` and `ra` (alias). `--no-interactive` skips clarifications and the review loop.

## Style Guidelines

- Respond in simple, easy-to-understand language. Keep answers short without irrelevant details.
- Avoid marketing language: do not use adjectives like "powerful", "built-in", "complete", "out-of-the-box", "hands-on", "essential", "production-ready", "makes it easy". Do not use phrases like "Check out", "Learn more", "Explore", "your needs", "choose the right...solution", "without changing your code", "automatically handles".
- Write for engineers — get into specifics and nuts-and-bolts details, not high-level benefit statements.
- Keep structure simple. Avoid deeply nested bullet points. Use emojis sparingly.

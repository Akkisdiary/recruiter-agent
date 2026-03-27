# Recruiter Agent

A CLI tool that enhances LaTeX resumes against job descriptions to improve ATS scores, keyword relevance, and chances of getting shortlisted.

It runs a multi-step LangGraph agent that acts as a senior recruiter — analyzing the job description, scoring your resume, asking clarifying questions about your experience, then rewriting your resume sections to better match the role.

## How it works

```
parse_resume → scrape_jd → score_before → ask_clarifications → enhance_resume → score_after → write_output
```

1. Parses your `.tex` resume into sections (preserving the LaTeX template)
2. Scrapes and analyzes the job description (from URL or text file)
3. Scores your current resume against the JD (before score)
4. Optionally asks you clarifying questions about your experience
5. Rewrites resume sections — rewords bullets, reorders by relevance, adds keywords, adds new points where supported
6. Scores the enhanced resume (after score)
7. Outputs a new `.tex` file and displays a before/after comparison table

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Create a `.env` file with your API key:

```bash
# Default provider is Google (Gemini)
GOOGLE_API_KEY=your-key-here

# Or use Anthropic/OpenAI
# ANTHROPIC_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here
```

## Usage

```bash
# Enhance using a JD text file
uv run recruiter-agent resume.tex --jd-file jd.txt

# Enhance using a JD URL
uv run recruiter-agent resume.tex --jd-url "https://example.com/job-posting"

# Skip clarifying questions
uv run recruiter-agent resume.tex --jd-file jd.txt --no-interactive

# Use a different provider/model
uv run recruiter-agent resume.tex --jd-file jd.txt --provider anthropic
uv run recruiter-agent resume.tex --jd-file jd.txt --provider openai --model gpt-4o

# Verbose output
uv run recruiter-agent resume.tex --jd-file jd.txt -v
```

Output is written to `<filename>_enhanced.tex` by default, or specify with `--output`.

## Example

```bash
uv run recruiter-agent examples/resume.tex --jd-file examples/jd.txt -v
```

Sample output:

```
            ATS Score Comparison
┏━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━┓
┃ Category       ┃ Before ┃ After ┃ Change ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━┩
│ Keyword Match  │   34   │  86   │  +52   │
│ Relevance      │   75   │  90   │  +15   │
│ Quantification │   95   │  95   │   0    │
│ Formatting     │   90   │  95   │   +5   │
│ Overall        │   67   │  90   │  +23   │
└────────────────┴────────┴───────┴────────┘
```

## Supported providers

| Provider | Flag | Default model | Env var |
|---|---|---|---|
| Google | `--provider google` (default) | `gemini-2.5-flash` | `GOOGLE_API_KEY` |
| Anthropic | `--provider anthropic` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `--provider openai` | `gpt-4o` | `OPENAI_API_KEY` |

## LaTeX handling

The tool preserves your resume's LaTeX template. It splits the `.tex` file into:
- **Preamble** (everything before `\begin{document}`) — untouched
- **Header** (name, contact info before first `\section*`) — untouched
- **Sections** (split on `\section*{}`) — enhanced by the LLM
- **Postamble** (`\end{document}`) — untouched

Post-processing escapes special characters (`&`, `#`, `%`) and restores proper line breaks. Validation uses `pylatexenc` to catch structural issues.

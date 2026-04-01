import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from recruiter_agent.agent.prompts import (
    CLARIFICATION_PROMPT,
    ENHANCEMENT_PROMPT,
    JD_ANALYSIS_PROMPT,
    SCORING_PROMPT,
    SYSTEM_PROMPT,
)
from recruiter_agent.agent.state import ResumeAgentState
from recruiter_agent.config import get_llm
from recruiter_agent.models.schemas import (
    ATSScore,
    ClarificationRequest,
    ClarifyingQA,
    EnhancedSections,
    JDAnalysis,
    ResumeSection,
)
from recruiter_agent.tools.latex import (
    escape_special_chars,
    format_latex,
    parse_latex,
    reconstruct_latex,
    validate_latex,
)
from recruiter_agent.tools.scraper import scrape_jd

console = Console()


def _get_llm(state: ResumeAgentState):
    return get_llm(
        provider=state.get("provider", "anthropic"),
        model=state.get("model"),
    )


def _postprocess_section(content: str) -> str:
    """Escape special chars, then format LaTeX content from LLM output."""
    content = escape_special_chars(content)
    content = format_latex(content)
    return content


def _sections_to_text(sections: list[ResumeSection]) -> str:
    parts = []
    for s in sections:
        if s.name == "__header__":
            parts.append(f"[Header/Contact Info]\n{s.content}")
        else:
            parts.append(f"[{s.name}]\n{s.content}")
    return "\n\n".join(parts)


def parse_resume_node(state: ResumeAgentState) -> dict:
    """Parse the LaTeX resume into preamble, sections, and postamble."""
    console.print("[bold blue]Step 1/7:[/] Parsing resume...", highlight=False)

    file_path = Path(state["resume_path"])
    raw_latex = file_path.read_text(encoding="utf-8")
    preamble, postamble, sections = parse_latex(file_path)

    if state.get("verbose"):
        console.print(f"  Found {len(sections)} sections: {[s.name for s in sections]}")

    return {
        "raw_latex": raw_latex,
        "preamble": preamble,
        "postamble": postamble,
        "sections": sections,
    }


def scrape_jd_node(state: ResumeAgentState) -> dict:
    """Scrape the job description URL and extract structured analysis."""
    console.print("[bold blue]Step 2/7:[/] Scraping job description...", highlight=False)

    jd_text_override = state.get("jd_text_override")
    if jd_text_override:
        jd_text = jd_text_override
        console.print("  Using provided JD text file")
    else:
        jd_text = scrape_jd(state["jd_url"])

    if state.get("verbose"):
        console.print(f"  Extracted {len(jd_text)} characters from JD")

    console.print("[bold blue]       [/] Analyzing job requirements...", highlight=False)

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(JDAnalysis)

    prompt = JD_ANALYSIS_PROMPT.format(jd_text=jd_text)
    jd_analysis = structured_llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    if state.get("verbose"):
        console.print(f"  Role: {jd_analysis.job_title} at {jd_analysis.company}")
        console.print(f"  Keywords: {', '.join(jd_analysis.keywords[:10])}...")

    return {
        "jd_raw_text": jd_text,
        "jd_analysis": jd_analysis,
    }


def _score_resume(state: ResumeAgentState, sections: list[ResumeSection]) -> ATSScore:
    """Score resume sections against the JD."""
    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(ATSScore)

    jd = state["jd_analysis"]
    prompt = SCORING_PROMPT.format(
        job_title=jd.job_title,
        company=jd.company,
        required_skills=", ".join(jd.required_skills),
        preferred_skills=", ".join(jd.preferred_skills),
        responsibilities=", ".join(jd.responsibilities),
        qualifications=", ".join(jd.qualifications),
        keywords=", ".join(jd.keywords),
        resume_content=_sections_to_text(sections),
    )

    return structured_llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )


def score_before_node(state: ResumeAgentState) -> dict:
    """Score the original resume against the JD."""
    console.print("[bold blue]Step 3/7:[/] Scoring original resume...", highlight=False)

    score = _score_resume(state, state["sections"])

    if state.get("verbose"):
        console.print(f"  Overall: {score.overall}/100")
        console.print(f"  Feedback: {score.feedback}")

    console.print(
        Panel(
            f"[bold]Overall: {score.overall}/100[/]\n"
            f"Keyword Match: {score.keyword_match} | Relevance: {score.relevance} | "
            f"Quantification: {score.quantification} | Formatting: {score.formatting}\n\n"
            f"[dim]{score.feedback}[/]",
            title="[red]Before Score[/]",
            border_style="red",
        )
    )

    return {"before_score": score}


def ask_clarifications_node(state: ResumeAgentState) -> dict:
    """Optionally ask the user clarifying questions about their experience."""
    console.print("[bold blue]Step 4/7:[/] Checking for gaps...", highlight=False)

    if state.get("no_interactive"):
        console.print("  Skipped (non-interactive mode)")
        return {"clarifying_qa": []}

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(ClarificationRequest)

    jd = state["jd_analysis"]
    score = state["before_score"]
    prompt = CLARIFICATION_PROMPT.format(
        job_title=jd.job_title,
        required_skills=", ".join(jd.required_skills),
        preferred_skills=", ".join(jd.preferred_skills),
        keywords=", ".join(jd.keywords),
        resume_content=_sections_to_text(state["sections"]),
        feedback=score.feedback,
        missing_keywords=", ".join(score.missing_keywords),
    )

    clarification = structured_llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    qa_pairs: list[ClarifyingQA] = []
    if clarification.needs_clarification and clarification.questions:
        console.print(
            "\n[bold yellow]I need to ask you a few questions to strengthen your resume:[/]\n"
        )
        for i, q in enumerate(clarification.questions, 1):
            console.print(f"[bold]{i}. {q.question}[/]")
            console.print(f"[dim]   Example: {q.example_answer}[/]")
            answer = console.input("[dim]Your answer (press Enter to skip): [/]")
            if answer.strip():
                qa_pairs.append(ClarifyingQA(question=q.question, answer=answer.strip()))
        console.print()
    else:
        console.print("  No clarifications needed")

    return {"clarifying_qa": qa_pairs}


def enhance_resume_node(state: ResumeAgentState) -> dict:
    """Enhance the resume sections based on JD analysis and scores."""
    console.print("[bold blue]Step 5/7:[/] Enhancing resume...", highlight=False)

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(EnhancedSections)

    jd = state["jd_analysis"]
    score = state["before_score"]

    # Build clarification context
    qa_pairs = state.get("clarifying_qa", [])
    if qa_pairs:
        qa_text = "Candidate's answers to clarifying questions:\n"
        for qa in qa_pairs:
            qa_text += f"Q: {qa.question}\nA: {qa.answer}\n\n"
        clarification_context = qa_text
    else:
        clarification_context = "No additional information from candidate."

    # Separate header from content sections — header is never sent to LLM
    header_section = None
    content_sections = []
    for s in state["sections"]:
        if s.name == "__header__":
            header_section = s
        else:
            content_sections.append(s)

    # Serialize only content sections for the prompt
    sections_json = json.dumps(
        [{"name": s.name, "content": s.content} for s in content_sections],
        indent=2,
    )

    prompt = ENHANCEMENT_PROMPT.format(
        job_title=jd.job_title,
        company=jd.company,
        required_skills=", ".join(jd.required_skills),
        preferred_skills=", ".join(jd.preferred_skills),
        responsibilities=", ".join(jd.responsibilities),
        keywords=", ".join(jd.keywords),
        before_score=score.overall,
        missing_keywords=", ".join(score.missing_keywords),
        feedback=score.feedback,
        clarification_context=clarification_context,
        sections_json=sections_json,
    )

    result = structured_llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    # Post-process: fix collapsed LaTeX formatting
    enhanced = []
    if header_section:
        enhanced.append(header_section)
    for s in result.sections:
        if s.name == "__header__":
            continue  # skip if LLM returned it anyway
        enhanced.append(ResumeSection(name=s.name, content=_postprocess_section(s.content)))

    if state.get("verbose"):
        console.print(f"  Enhanced {len(enhanced)} sections")

    return {"enhanced_sections": enhanced}


def score_after_node(state: ResumeAgentState) -> dict:
    """Score the enhanced resume."""
    console.print("[bold blue]Step 6/7:[/] Scoring enhanced resume...", highlight=False)

    score = _score_resume(state, state["enhanced_sections"])

    console.print(
        Panel(
            f"[bold]Overall: {score.overall}/100[/]\n"
            f"Keyword Match: {score.keyword_match} | Relevance: {score.relevance} | "
            f"Quantification: {score.quantification} | Formatting: {score.formatting}\n\n"
            f"[dim]{score.feedback}[/]",
            title="[green]After Score[/]",
            border_style="green",
        )
    )

    return {"after_score": score}


def write_output_node(state: ResumeAgentState) -> dict:
    """Reconstruct and write the enhanced .tex file."""
    console.print("[bold blue]Step 7/7:[/] Writing enhanced resume...", highlight=False)

    enhanced_latex = reconstruct_latex(
        state["preamble"],
        state["postamble"],
        state["enhanced_sections"],
    )

    # Validate only the document body (between \begin{document} and \end{document})
    # to avoid false positives on LaTeX comments in the preamble
    body_content = "\n".join(
        s.content for s in state["enhanced_sections"]
    )
    warnings = validate_latex(body_content)
    if warnings:
        console.print("[yellow]LaTeX validation warnings:[/]")
        for w in warnings:
            console.print(f"  [yellow]- {w}[/]")

    # Write output
    output_path = Path(state["output_path"])
    output_path.write_text(enhanced_latex, encoding="utf-8")

    return {"enhanced_latex": enhanced_latex}

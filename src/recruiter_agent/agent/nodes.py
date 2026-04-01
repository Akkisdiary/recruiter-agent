import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from rich.console import Console
from rich.panel import Panel

from recruiter_agent.agent.prompts import (
    CHANGE_SUMMARY_PROMPT,
    CLARIFICATION_PROMPT,
    JD_ANALYSIS_PROMPT,
    RECRUITER_INSTRUCTION_PROMPT,
    RECRUITER_REVISION_PROMPT,
    RECRUITER_SYSTEM_PROMPT,
    SCORING_PROMPT,
    WRITER_ENHANCE_PROMPT,
    WRITER_REVISION_PROMPT,
    WRITER_SYSTEM_PROMPT,
)
from recruiter_agent.agent.state import ResumeAgentState
from recruiter_agent.config import get_llm
from recruiter_agent.models.schemas import (
    ATSScore,
    ClarificationRequest,
    ClarifyingQA,
    EnhancedSections,
    JDAnalysis,
    ResumeContent,
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


def _format_content_for_writer(content: ResumeContent) -> str:
    """Render ResumeContent as readable text for the writer agent."""
    parts = []
    for section in content.sections:
        parts.append(f"--- Section: {section.name} ---")
        parts.append(section.content)
        parts.append("")
    return "\n".join(parts)


# --- Utility nodes (no agent context needed) ---


def parse_resume_node(state: ResumeAgentState) -> dict:
    """Parse the LaTeX resume into preamble, sections, and postamble."""
    console.print(
        "[bold blue]Step 1:[/] Parsing resume...", highlight=False
    )

    file_path = Path(state["resume_path"])
    raw_latex = file_path.read_text(encoding="utf-8")
    preamble, postamble, sections = parse_latex(file_path)

    if state.get("verbose"):
        console.print(
            f"  Found {len(sections)} sections: {[s.name for s in sections]}"
        )

    return {
        "raw_latex": raw_latex,
        "preamble": preamble,
        "postamble": postamble,
        "sections": sections,
    }


def scrape_jd_node(state: ResumeAgentState) -> dict:
    """Scrape the job description URL and extract structured analysis."""
    console.print(
        "[bold blue]Step 2:[/] Scraping job description...", highlight=False
    )

    jd_text_override = state.get("jd_text_override")
    if jd_text_override:
        jd_text = jd_text_override
        console.print("  Using provided JD text file")
    else:
        jd_text = scrape_jd(state["jd_url"])

    if state.get("verbose"):
        console.print(f"  Extracted {len(jd_text)} characters from JD")

    console.print(
        "[bold blue]       [/] Analyzing job requirements...", highlight=False
    )

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(JDAnalysis)

    prompt = JD_ANALYSIS_PROMPT.format(jd_text=jd_text)
    jd_analysis = structured_llm.invoke(
        [
            {"role": "system", "content": RECRUITER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    if state.get("verbose"):
        console.print(
            f"  Role: {jd_analysis.job_title} at {jd_analysis.company}"
        )
        console.print(
            f"  Keywords: {', '.join(jd_analysis.keywords[:10])}..."
        )

    return {
        "jd_raw_text": jd_text,
        "jd_analysis": jd_analysis,
    }


# --- Recruiter Agent nodes ---


def score_before_node(state: ResumeAgentState) -> dict:
    """Score the original resume and seed the recruiter's message history."""
    console.print(
        "[bold blue]Step 3:[/] Scoring original resume...", highlight=False
    )

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(ATSScore)

    jd = state["jd_analysis"]
    resume_text = _sections_to_text(state["sections"])

    prompt = SCORING_PROMPT.format(
        job_title=jd.job_title,
        company=jd.company,
        required_skills=", ".join(jd.required_skills),
        preferred_skills=", ".join(jd.preferred_skills),
        responsibilities=", ".join(jd.responsibilities),
        qualifications=", ".join(jd.qualifications),
        keywords=", ".join(jd.keywords),
        resume_content=resume_text,
    )

    score = structured_llm.invoke(
        [
            {"role": "system", "content": RECRUITER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

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

    # Seed the recruiter's message history with full context
    jd_summary = (
        f"Job: {jd.job_title} at {jd.company}\n"
        f"Required: {', '.join(jd.required_skills)}\n"
        f"Preferred: {', '.join(jd.preferred_skills)}\n"
        f"Responsibilities: {', '.join(jd.responsibilities)}\n"
        f"Keywords: {', '.join(jd.keywords)}"
    )
    context_msg = HumanMessage(
        content=(
            f"Here is the candidate's resume:\n\n{resume_text}\n\n"
            f"Here is the job description analysis:\n\n{jd_summary}\n\n"
            f"ATS Score: {score.overall}/100\n"
            f"Feedback: {score.feedback}\n"
            f"Missing keywords: {', '.join(score.missing_keywords)}"
        )
    )
    ack_msg = AIMessage(
        content=(
            f"I've reviewed the resume against the JD. "
            f"Score is {score.overall}/100. {score.feedback}"
        )
    )

    return {
        "before_score": score,
        "recruiter_messages": [
            SystemMessage(content=RECRUITER_SYSTEM_PROMPT),
            context_msg,
            ack_msg,
        ],
    }


def ask_clarifications_node(state: ResumeAgentState) -> dict:
    """Ask clarifying questions using the recruiter's accumulated context."""
    console.print(
        "[bold blue]Step 4:[/] Checking for gaps...", highlight=False
    )

    if state.get("no_interactive"):
        console.print("  Skipped (non-interactive mode)")
        return {"clarifying_qa": []}

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(ClarificationRequest)

    # Use recruiter's message history + clarification request
    user_msg = HumanMessage(content=CLARIFICATION_PROMPT)
    messages = list(state.get("recruiter_messages", [])) + [user_msg]

    clarification = structured_llm.invoke(messages)

    qa_pairs: list[ClarifyingQA] = []
    new_messages = [user_msg]

    if clarification.needs_clarification and clarification.questions:
        console.print(
            "\n[bold yellow]I need to ask you a few questions to strengthen your resume:[/]\n"
        )
        for i, q in enumerate(clarification.questions, 1):
            console.print(f"[bold]{i}. {q.question}[/]")
            console.print(f"[dim]   Example: {q.example_answer}[/]")
            answer = console.input(
                "[dim]Your answer (press Enter to skip): [/]"
            )
            if answer.strip():
                qa_pairs.append(
                    ClarifyingQA(
                        question=q.question, answer=answer.strip()
                    )
                )
        console.print()

        # Add Q&A to recruiter's history so it remembers the answers
        if qa_pairs:
            qa_text = "Candidate's answers:\n"
            for qa in qa_pairs:
                qa_text += f"Q: {qa.question}\nA: {qa.answer}\n"
            new_messages.append(
                AIMessage(content="I asked clarifying questions.")
            )
            new_messages.append(HumanMessage(content=qa_text))
        else:
            new_messages.append(
                AIMessage(
                    content="I asked questions but the candidate skipped them."
                )
            )
    else:
        console.print("  No clarifications needed")
        new_messages.append(
            AIMessage(content="No clarifications needed.")
        )

    return {
        "clarifying_qa": qa_pairs,
        "recruiter_messages": new_messages,
    }


def recruiter_instruct_node(state: ResumeAgentState) -> dict:
    """Recruiter writes the final resume content in plain text."""
    console.print(
        "[bold blue]Step 5:[/] Writing enhanced content...", highlight=False
    )

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(ResumeContent)

    user_msg = HumanMessage(content=RECRUITER_INSTRUCTION_PROMPT)
    messages = list(state.get("recruiter_messages", [])) + [user_msg]

    content = structured_llm.invoke(messages)

    if state.get("verbose"):
        console.print(
            f"  Sections: {[s.name for s in content.sections]}"
        )

    ai_msg = AIMessage(content=content.model_dump_json())

    return {
        "resume_content": content,
        "recruiter_messages": [user_msg, ai_msg],
    }


def recruiter_revise_instruct_node(state: ResumeAgentState) -> dict:
    """Recruiter rewrites the resume content based on user feedback."""
    revision_count = state.get("revision_count", 0)
    console.print(
        f"[bold blue]Revision {revision_count}:[/] Revising content...",
        highlight=False,
    )

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(ResumeContent)

    revision_feedback = state.get("revision_feedback", "")
    user_msg = HumanMessage(
        content=RECRUITER_REVISION_PROMPT.format(
            revision_feedback=revision_feedback,
        )
    )
    messages = list(state.get("recruiter_messages", [])) + [user_msg]

    content = structured_llm.invoke(messages)

    if state.get("verbose"):
        console.print(
            f"  Revised sections: {[s.name for s in content.sections]}"
        )

    ai_msg = AIMessage(content=content.model_dump_json())

    return {
        "resume_content": content,
        "recruiter_messages": [user_msg, ai_msg],
    }


# --- LaTeX Expert (Writer) Agent nodes ---


def latex_expert_enhance_node(state: ResumeAgentState) -> dict:
    """Writer formats the recruiter's plain text content into LaTeX."""
    revision_count = state.get("revision_count", 0)
    is_revision = revision_count > 0 and state.get("revision_feedback")

    if is_revision:
        console.print(
            f"[bold blue]Revision {revision_count}:[/] Formatting to LaTeX...",
            highlight=False,
        )
    else:
        console.print(
            "[bold blue]Step 6:[/] Formatting to LaTeX...", highlight=False
        )

    llm = _get_llm(state)
    structured_llm = llm.with_structured_output(EnhancedSections)

    content = state["resume_content"]
    content_text = _format_content_for_writer(content)

    # Separate header from content sections (for reference)
    header_section = None
    content_sections = []
    source_sections = (
        state.get("enhanced_sections") if is_revision else state["sections"]
    )
    for s in source_sections:
        if s.name == "__header__":
            header_section = s
        else:
            content_sections.append(s)

    sections_json = json.dumps(
        [{"name": s.name, "content": s.content} for s in content_sections],
        indent=2,
    )

    if is_revision:
        prompt_text = WRITER_REVISION_PROMPT.format(
            resume_content=content_text,
            sections_json=sections_json,
        )
    else:
        prompt_text = WRITER_ENHANCE_PROMPT.format(
            resume_content=content_text,
            sections_json=sections_json,
        )

    # Writer gets its own message history
    user_msg = HumanMessage(content=prompt_text)
    if is_revision:
        messages = list(state.get("writer_messages", [])) + [user_msg]
    else:
        messages = [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            user_msg,
        ]

    result = structured_llm.invoke(messages)

    # Post-process: fix collapsed LaTeX formatting
    enhanced = []
    if header_section:
        enhanced.append(header_section)
    for s in result.sections:
        if s.name == "__header__":
            continue
        enhanced.append(
            ResumeSection(
                name=s.name, content=_postprocess_section(s.content)
            )
        )

    if state.get("verbose"):
        console.print(f"  Formatted {len(enhanced)} sections")

    ai_msg = AIMessage(content="Formatted to LaTeX.")
    new_writer_messages = (
        [user_msg, ai_msg]
        if is_revision
        else [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            user_msg,
            ai_msg,
        ]
    )

    return {
        "enhanced_sections": enhanced,
        "writer_messages": new_writer_messages,
    }


# --- Scoring (uses recruiter context) ---


def score_after_node(state: ResumeAgentState) -> dict:
    """Score the enhanced resume."""
    revision_count = state.get("revision_count", 0)
    if revision_count > 0:
        console.print(
            f"[bold blue]Revision {revision_count}:[/] Scoring revised resume...",
            highlight=False,
        )
    else:
        console.print(
            "[bold blue]Step 7:[/] Scoring enhanced resume...",
            highlight=False,
        )

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
        resume_content=_sections_to_text(state["enhanced_sections"]),
    )

    score = structured_llm.invoke(
        [
            {"role": "system", "content": RECRUITER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

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

    # Add score to recruiter's history for revision context
    score_msg = HumanMessage(
        content=(
            f"Enhanced resume scored {score.overall}/100. "
            f"Feedback: {score.feedback}"
        )
    )
    ack_msg = AIMessage(content="Noted the after-score.")

    return {
        "after_score": score,
        "recruiter_messages": [score_msg, ack_msg],
    }


# --- Review & output nodes ---


def _get_change_summary(state: ResumeAgentState) -> str:
    """Ask the LLM to summarize changes between original and enhanced sections."""
    llm = _get_llm(state)

    original = _sections_to_text(state["sections"])
    enhanced = _sections_to_text(state["enhanced_sections"])

    prompt = CHANGE_SUMMARY_PROMPT.format(
        original_sections=original,
        enhanced_sections=enhanced,
    )

    response = llm.invoke(
        [
            {"role": "system", "content": RECRUITER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
    return response.content


def review_changes_node(state: ResumeAgentState) -> dict:
    """Show changes to the user and ask for feedback."""
    if state.get("no_interactive"):
        return {
            "revision_feedback": None,
            "revision_count": state.get("revision_count", 0),
        }

    console.print()
    console.print("[bold yellow]Here's what I changed:[/]\n")
    summary = _get_change_summary(state)
    console.print(
        Panel(summary, border_style="yellow", title="Change Summary")
    )

    console.print()
    console.print("[bold]Options:[/]")
    console.print(
        "  [bold green]a[/] — Accept and save the enhanced resume"
    )
    console.print(
        "  [bold yellow]f[/] — Give feedback for another revision"
    )
    console.print()

    while True:
        choice = (
            console.input("[bold]Your choice (a/f): [/]").strip().lower()
        )
        if choice in ("a", "f"):
            break
        console.print(
            "[red]  Please enter 'a' to accept or 'f' for feedback[/]"
        )

    if choice == "a":
        return {
            "revision_feedback": None,
            "revision_count": state.get("revision_count", 0),
        }

    console.print()
    feedback = console.input(
        "[bold yellow]What would you like changed? [/]\n"
        "[dim](Be specific — e.g. 'tone down the ML bullet, I only used scikit-learn' "
        "or 'keep the original wording for my last job')[/]\n> "
    )

    return {
        "revision_feedback": feedback.strip() or None,
        "revision_count": state.get("revision_count", 0) + 1,
    }


def write_output_node(state: ResumeAgentState) -> dict:
    """Reconstruct and write the enhanced .tex file."""
    console.print(
        "[bold blue]Writing enhanced resume...[/]", highlight=False
    )

    enhanced_latex = reconstruct_latex(
        state["preamble"],
        state["postamble"],
        state["enhanced_sections"],
    )

    body_content = "\n".join(
        s.content for s in state["enhanced_sections"]
    )
    warnings = validate_latex(body_content)
    if warnings:
        console.print("[yellow]LaTeX validation warnings:[/]")
        for w in warnings:
            console.print(f"  [yellow]- {w}[/]")

    output_path = Path(state["output_path"])
    output_path.write_text(enhanced_latex, encoding="utf-8")

    return {"enhanced_latex": enhanced_latex}

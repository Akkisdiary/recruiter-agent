from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from recruiter_agent.models.schemas import (
    ATSScore,
    ClarifyingQA,
    JDAnalysis,
    ResumeContent,
    ResumeSection,
)


class ResumeAgentState(TypedDict, total=False):
    # Inputs
    resume_path: str
    jd_url: str
    output_path: str
    provider: str
    model: str | None
    no_interactive: bool
    verbose: bool
    jd_text_override: str | None

    # Parsed resume
    raw_latex: str
    preamble: str
    postamble: str
    sections: list[ResumeSection]

    # JD analysis
    jd_raw_text: str
    jd_analysis: JDAnalysis

    # Scoring
    before_score: ATSScore
    after_score: ATSScore

    # Clarification
    clarifying_qa: list[ClarifyingQA]

    # Resume content (recruiter -> writer contract)
    resume_content: ResumeContent

    # Enhanced output
    enhanced_sections: list[ResumeSection]
    enhanced_latex: str

    # Review loop
    revision_feedback: str | None
    revision_count: int

    # Per-agent message histories (add_messages appends, not replaces)
    recruiter_messages: Annotated[list[BaseMessage], add_messages]
    writer_messages: Annotated[list[BaseMessage], add_messages]

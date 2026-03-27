from typing import TypedDict

from recruiter_agent.models.schemas import (
    ATSScore,
    ClarifyingQA,
    JDAnalysis,
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

    # Enhanced output
    enhanced_sections: list[ResumeSection]
    enhanced_latex: str

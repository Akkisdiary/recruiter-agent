from pydantic import BaseModel, Field


class ResumeSection(BaseModel):
    name: str = Field(description="Section name, e.g. 'Experience', 'Education'. Use '__header__' for content before the first section.")
    content: str = Field(description="Raw LaTeX content of the section (without the \\section*{} command itself)")


class JDAnalysis(BaseModel):
    job_title: str = Field(description="Job title from the posting")
    company: str = Field(description="Company name")
    required_skills: list[str] = Field(description="Skills explicitly listed as required")
    preferred_skills: list[str] = Field(description="Skills listed as preferred or nice-to-have")
    responsibilities: list[str] = Field(description="Key responsibilities of the role")
    qualifications: list[str] = Field(description="Required qualifications (education, years of experience, etc.)")
    keywords: list[str] = Field(description="Important keywords and phrases for ATS matching")


class ATSScore(BaseModel):
    keyword_match: int = Field(ge=0, le=100, description="Percentage of JD keywords found in resume")
    relevance: int = Field(ge=0, le=100, description="How well experiences align with the role")
    quantification: int = Field(ge=0, le=100, description="How well achievements are quantified with metrics")
    formatting: int = Field(ge=0, le=100, description="Structure, conciseness, and clarity of content")
    overall: int = Field(ge=0, le=100, description="Weighted average: keyword(35%) + relevance(30%) + quantification(20%) + formatting(15%)")
    missing_keywords: list[str] = Field(description="Important JD keywords not found in the resume")
    feedback: str = Field(description="Direct, honest feedback about the resume's fit for this role")


class ClarifyingQA(BaseModel):
    question: str
    answer: str


class ClarificationQuestion(BaseModel):
    question: str = Field(description="A simple, specific question in plain language about one missing skill or experience")
    example_answer: str = Field(description="A short, realistic example answer showing the kind of detail expected")


class ClarificationRequest(BaseModel):
    needs_clarification: bool = Field(description="Whether clarifying questions are needed")
    questions: list[ClarificationQuestion] = Field(description="Questions to ask the candidate, empty if needs_clarification is False")


class EnhancedSections(BaseModel):
    sections: list[ResumeSection] = Field(description="Enhanced resume sections with modified LaTeX content")

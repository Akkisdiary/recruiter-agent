from langgraph.graph import END, StateGraph

from recruiter_agent.agent.nodes import (
    ask_clarifications_node,
    enhance_resume_node,
    parse_resume_node,
    review_changes_node,
    score_after_node,
    score_before_node,
    scrape_jd_node,
    write_output_node,
)
from recruiter_agent.agent.state import ResumeAgentState


def _should_revise(state: ResumeAgentState) -> str:
    """Route after review: revise if user gave feedback, otherwise write output."""
    if state.get("revision_feedback"):
        return "enhance_resume"
    return "write_output"


def build_graph() -> StateGraph:
    """Build the resume enhancement agent graph."""
    graph = StateGraph(ResumeAgentState)

    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("scrape_jd", scrape_jd_node)
    graph.add_node("score_before", score_before_node)
    graph.add_node("ask_clarifications", ask_clarifications_node)
    graph.add_node("enhance_resume", enhance_resume_node)
    graph.add_node("score_after", score_after_node)
    graph.add_node("review_changes", review_changes_node)
    graph.add_node("write_output", write_output_node)

    graph.set_entry_point("parse_resume")
    graph.add_edge("parse_resume", "scrape_jd")
    graph.add_edge("scrape_jd", "score_before")
    graph.add_edge("score_before", "ask_clarifications")
    graph.add_edge("ask_clarifications", "enhance_resume")
    graph.add_edge("enhance_resume", "score_after")
    graph.add_edge("score_after", "review_changes")
    graph.add_conditional_edges("review_changes", _should_revise)
    graph.add_edge("write_output", END)

    return graph


def create_app():
    """Create and compile the agent graph."""
    graph = build_graph()
    return graph.compile()

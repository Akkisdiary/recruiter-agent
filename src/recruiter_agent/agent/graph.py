from langgraph.graph import END, StateGraph

from recruiter_agent.agent.nodes import (
    ask_clarifications_node,
    latex_expert_enhance_node,
    parse_resume_node,
    recruiter_instruct_node,
    recruiter_revise_instruct_node,
    review_changes_node,
    score_after_node,
    score_before_node,
    scrape_jd_node,
    write_output_node,
)
from recruiter_agent.agent.state import ResumeAgentState


def _should_revise(state: ResumeAgentState) -> str:
    """Route after review: revise (through recruiter) or write output."""
    if state.get("revision_feedback"):
        return "recruiter_revise_instruct"
    return "write_output"


def build_graph() -> StateGraph:
    """Build the resume enhancement agent graph.

    Flow:
      parse_resume -> scrape_jd -> score_before -> ask_clarifications
        -> recruiter_instruct -> latex_expert_enhance -> score_after
        -> review_changes -> [accept] write_output -> END
                          -> [feedback] recruiter_revise_instruct
                             -> latex_expert_enhance (loop)
    """
    graph = StateGraph(ResumeAgentState)

    # Utility nodes
    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("scrape_jd", scrape_jd_node)
    graph.add_node("write_output", write_output_node)

    # Recruiter agent nodes
    graph.add_node("score_before", score_before_node)
    graph.add_node("ask_clarifications", ask_clarifications_node)
    graph.add_node("recruiter_instruct", recruiter_instruct_node)
    graph.add_node(
        "recruiter_revise_instruct", recruiter_revise_instruct_node
    )
    graph.add_node("score_after", score_after_node)

    # Writer agent node
    graph.add_node("latex_expert_enhance", latex_expert_enhance_node)

    # Review node
    graph.add_node("review_changes", review_changes_node)

    # Edges
    graph.set_entry_point("parse_resume")
    graph.add_edge("parse_resume", "scrape_jd")
    graph.add_edge("scrape_jd", "score_before")
    graph.add_edge("score_before", "ask_clarifications")
    graph.add_edge("ask_clarifications", "recruiter_instruct")
    graph.add_edge("recruiter_instruct", "latex_expert_enhance")
    graph.add_edge("latex_expert_enhance", "score_after")
    graph.add_edge("score_after", "review_changes")
    graph.add_conditional_edges("review_changes", _should_revise)
    graph.add_edge("recruiter_revise_instruct", "latex_expert_enhance")
    graph.add_edge("write_output", END)

    return graph


def create_app():
    """Create and compile the agent graph."""
    graph = build_graph()
    return graph.compile()

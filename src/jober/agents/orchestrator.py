"""LangGraph orchestrator: builds the init and apply graphs."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from jober.agents.cv_latex_writer import cv_latex_writer_node
from jober.agents.cv_reader import cv_reader_node
from jober.agents.cv_writer import cv_writer_node
from jober.agents.job_scraper import job_scraper_node
from jober.agents.offer_evaluator import offer_evaluator_node
from jober.agents.onboarding import merge_profile_node, onboarding_interview_node
from jober.core.state import JoberState, view_state


def _should_continue_onboarding(state: JoberState) -> str:
    """Route onboarding to merge or pause for user input."""
    state = view_state(state)
    if state.next_step == "merge_profile":
        return "merge_profile"
    return END


def build_init_graph() -> StateGraph:
    """Build the graph for `jober init`."""
    graph = StateGraph(JoberState)

    graph.add_node("cv_reader", cv_reader_node)
    graph.add_node("onboarding", onboarding_interview_node)
    graph.add_node("merge_profile", merge_profile_node)

    graph.set_entry_point("cv_reader")
    graph.add_edge("cv_reader", "onboarding")
    graph.add_conditional_edges(
        "onboarding",
        _should_continue_onboarding,
        {
            "merge_profile": "merge_profile",
            END: END,
        },
    )
    graph.add_edge("merge_profile", END)

    return graph.compile()


def _should_continue_apply(state: JoberState) -> str:
    """Route after scraping."""
    state = view_state(state)
    if state.error:
        return END
    return "offer_evaluator"


def _should_continue_after_evaluation(state: JoberState) -> str:
    """Route after local evaluation."""
    state = view_state(state)
    if state.error:
        return END
    if not state.should_apply:
        return END
    return "cv_latex_writer"


def build_apply_graph() -> StateGraph:
    """Build the graph for `jober apply`."""
    graph = StateGraph(JoberState)

    graph.add_node("job_scraper", job_scraper_node)
    graph.add_node("offer_evaluator", offer_evaluator_node)
    graph.add_node("cv_latex_writer", cv_latex_writer_node)
    graph.add_node("cv_writer", cv_writer_node)

    graph.set_entry_point("job_scraper")
    graph.add_conditional_edges(
        "job_scraper",
        _should_continue_apply,
        {
            "offer_evaluator": "offer_evaluator",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "offer_evaluator",
        _should_continue_after_evaluation,
        {
            "cv_latex_writer": "cv_latex_writer",
            END: END,
        },
    )
    graph.add_edge("cv_latex_writer", "cv_writer")
    graph.add_edge("cv_writer", END)

    return graph.compile()

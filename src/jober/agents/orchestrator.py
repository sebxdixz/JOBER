"""Orquestador multiagente LangGraph — define los grafos para init y apply."""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from jober.core.state import JoberState
from jober.agents.cv_reader import cv_reader_node
from jober.agents.cv_writer import cv_writer_node
from jober.agents.job_scraper import job_scraper_node
from jober.agents.offer_evaluator import offer_evaluator_node
from jober.agents.onboarding import onboarding_interview_node, merge_profile_node


# ── Grafo: jober init ──────────────────────────────────────────────────────
# Flujo: read_cvs → onboarding_interview → (loop con usuario) → merge_profile

def _should_continue_onboarding(state: JoberState) -> str:
    """Router: si el onboarding terminó, merge; si no, esperar input."""
    if state.next_step == "merge_profile":
        return "merge_profile"
    return END  # Pausar para input del usuario


def build_init_graph() -> StateGraph:
    """Construye el grafo para el comando `jober init`."""
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


# ── Grafo: jober apply ─────────────────────────────────────────────────────
# Flujo: scrape_job → cv_writer → END

def _should_continue_apply(state: JoberState) -> str:
    """Router post-scraping."""
    if state.error:
        return END
    return "offer_evaluator"


def _should_continue_after_evaluation(state: JoberState) -> str:
    """Router post-evaluacion."""
    if state.error:
        return END
    if not state.should_apply:
        return END
    return "cv_writer"


def build_apply_graph() -> StateGraph:
    """Construye el grafo para el comando `jober apply`."""
    graph = StateGraph(JoberState)

    graph.add_node("job_scraper", job_scraper_node)
    graph.add_node("offer_evaluator", offer_evaluator_node)
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
            "cv_writer": "cv_writer",
            END: END,
        },
    )
    graph.add_edge("cv_writer", END)

    return graph.compile()

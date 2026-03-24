"""Dedicated CV creation agent.

Generates LaTeX as the primary CV artifact and Markdown as the fallback mirror.
"""

from __future__ import annotations

from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from jober.core.config import get_llm
from jober.core.logging import logger
from jober.core.prompts import get_prompt
from jober.core.state import JoberState, view_state
from jober.utils.language_detection import detect_offer_document_language
from jober.utils.llm_helpers import ainvoke_with_retry


async def cv_latex_writer_node(state: JoberState) -> dict:
    """Generate the adapted CV using a dedicated LaTeX-first agent."""
    state = view_state(state)
    llm = get_llm()

    perfil_json = state.perfil.model_dump_json(indent=2)
    oferta_json = state.oferta.model_dump_json(indent=2)
    today = date.today().strftime("%Y-%m-%d")
    document_language = _detect_offer_language(state)
    context = (
        f"FECHA_ACTUAL: {today}\n\n"
        f"IDIOMA_DOCUMENTO: {document_language}\n\n"
        f"PERFIL:\n{perfil_json}\n\n"
        f"OFERTA:\n{oferta_json}"
    )

    try:
        cv_latex = await _call_with_retry(
            llm,
            get_prompt("cv_latex_writer_cv_latex"),
            context,
            "latex cv generation",
        )
        cv_markdown = await _call_with_retry(
            llm,
            get_prompt("cv_latex_writer_cv_markdown"),
            context,
            "markdown cv generation",
        )
    except Exception as exc:
        logger.exception(
            "CV generation failed for {} at {}",
            state.oferta.empresa or "(sin empresa)",
            state.oferta.url or "(sin url)",
        )
        return {"error": f"Error generando CV adaptado con LLM: {exc}"}

    docs = state.documentos.model_copy(deep=True)
    docs.cv_adaptado_tex = cv_latex.strip()
    docs.cv_adaptado_md = cv_markdown.strip()

    return {
        "documentos": docs,
        "current_agent": "cv_latex_writer",
        "next_step": "cv_writer",
    }


async def _call_with_retry(llm, system_prompt: str, context: str, operation: str) -> str:
    response = await ainvoke_with_retry(
        llm,
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context),
        ],
        operation=operation,
    )
    return str(response.content)


def _detect_offer_language(state: JoberState) -> str:
    state = view_state(state)
    return detect_offer_document_language(state.oferta)

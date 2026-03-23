"""Agente escritor de CV — genera CV adaptado y cover letter para una oferta."""

from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from jober.core.config import get_llm
from jober.core.models import DocumentosGenerados
from jober.core.state import JoberState
from jober.utils.llm_helpers import strip_markdown_fences


CV_SYSTEM_PROMPT = """Eres un experto en redacción de CVs profesionales.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo con sus requisitos

Tu tarea es generar un CV en formato Markdown que:
- Resalte las experiencias y habilidades MÁS relevantes para esta oferta específica
- Reorganice las secciones para que lo más relevante aparezca primero
- Use keywords de la oferta de forma natural
- Sea conciso (máximo 2 páginas si se imprimiera)
- Tenga un resumen profesional adaptado a la oferta

Responde SOLO con el CV en Markdown limpio, listo para exportar."""


COVER_LETTER_PROMPT = """Eres un experto en redacción de cartas de presentación.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo

Genera una carta de presentación en Markdown que:
- Sea personalizada para la empresa y el cargo
- Conecte experiencias concretas del candidato con los requisitos
- Sea profesional pero con personalidad
- Tenga máximo 3-4 párrafos
- NO sea genérica

Responde SOLO con la carta en Markdown."""


MATCH_ANALYSIS_PROMPT = """Eres un analista de fit laboral.
Recibirás:
1. El perfil maestro del candidato
2. La oferta de trabajo

Analiza el match entre candidato y oferta:
1. match_score: número entre 0.0 y 1.0
2. analisis_fit: texto breve (3-5 oraciones) explicando fortalezas y gaps

Responde en JSON exacto:
{{"match_score": 0.85, "analisis_fit": "..."}}"""


async def cv_writer_node(state: JoberState) -> dict:
    """Nodo LangGraph: genera CV adaptado, cover letter y análisis de fit."""
    llm = get_llm()

    perfil_json = state.perfil.model_dump_json(indent=2)
    oferta_json = state.oferta.model_dump_json(indent=2)
    context = f"PERFIL:\n{perfil_json}\n\nOFERTA:\n{oferta_json}"

    cv_resp, cl_resp, match_resp = await _generate_all(llm, context)

    docs = DocumentosGenerados(
        cv_adaptado_md=cv_resp,
        cover_letter_md=cl_resp,
    )

    try:
        import json
        clean_match = strip_markdown_fences(match_resp)
        match_data = json.loads(clean_match)
        docs.match_score = float(match_data.get("match_score", 0))
        docs.analisis_fit = match_data.get("analisis_fit", "")
    except Exception:
        docs.analisis_fit = match_resp

    return {
        "documentos": docs,
        "current_agent": "cv_writer",
        "next_step": "save_output",
    }


async def _generate_all(llm: ChatOpenAI, context: str) -> tuple[str, str, str]:
    """Genera CV, cover letter y match analysis en paralelo."""
    import asyncio

    async def _call(system: str) -> str:
        resp = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=context),
        ])
        return resp.content

    cv_task = _call(CV_SYSTEM_PROMPT)
    cl_task = _call(COVER_LETTER_PROMPT)
    match_task = _call(MATCH_ANALYSIS_PROMPT)

    results = await asyncio.gather(cv_task, cl_task, match_task)
    return results[0], results[1], results[2]

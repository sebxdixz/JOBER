"""Dedicated CV creation agent.

Generates LaTeX as the primary CV artifact and Markdown as the fallback/rendering mirror.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jober.core.config import get_llm
from jober.core.state import JoberState


CV_LATEX_PROMPT = r"""Eres un experto en CVs técnicos y redacción en LaTeX.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo (JSON)

Genera un CV adaptado en LaTeX.

Reglas:
- Devuelve un documento LaTeX COMPLETO y compilable con `pdflatex`
- Usa `article`, `geometry`, `enumitem`, `hyperref`
- Diseño limpio, ATS-friendly, una columna
- Máximo 2 páginas
- Incluye: encabezado con contacto, resumen, experiencia, habilidades, educación, idiomas
- Reordena y enfatiza la experiencia más relevante para la oferta
- Usa keywords reales de la oferta de forma natural
- NO inventes información
- Escapa correctamente caracteres de LaTeX
- Si falta un dato de contacto, omítelo

Responde SOLO con el código LaTeX, sin fences ni explicaciones."""


CV_MARKDOWN_PROMPT = """Eres un experto en redacción de CVs profesionales.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo (JSON)

Genera un CV adaptado en Markdown con el mismo contenido del CV final.

Reglas:
- Encabezado con nombre y contacto
- Resumen profesional
- Experiencia relevante primero
- Habilidades, educación e idiomas
- Máximo 2 páginas al renderizar
- No inventes información

Responde SOLO con el CV en Markdown."""


async def cv_latex_writer_node(state: JoberState) -> dict:
    """Generate the adapted CV using a dedicated LaTeX-first agent."""
    llm = get_llm()

    perfil_json = state.perfil.model_dump_json(indent=2)
    oferta_json = state.oferta.model_dump_json(indent=2)
    context = f"PERFIL:\n{perfil_json}\n\nOFERTA:\n{oferta_json}"

    cv_latex = await _call_with_retry(llm, CV_LATEX_PROMPT, context)
    cv_markdown = await _call_with_retry(llm, CV_MARKDOWN_PROMPT, context)

    docs = state.documentos.model_copy(deep=True)
    docs.cv_adaptado_tex = cv_latex.strip()
    docs.cv_adaptado_md = cv_markdown.strip()

    return {
        "documentos": docs,
        "current_agent": "cv_latex_writer",
        "next_step": "cv_writer",
    }


async def _call_with_retry(llm: ChatOpenAI, system_prompt: str, context: str, max_retries: int = 3) -> str:
    import asyncio

    for attempt in range(max_retries):
        try:
            resp = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=context),
            ])
            return resp.content
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                await asyncio.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("Max retries exceeded for CV generation")

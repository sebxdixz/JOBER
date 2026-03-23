"""Dedicated CV creation agent.

Generates LaTeX as the primary CV artifact and Markdown as the fallback/rendering mirror.
"""

from __future__ import annotations

from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jober.core.config import get_llm
from jober.core.state import JoberState


CV_LATEX_PROMPT = r"""Eres un CV strategist senior y un experto en LaTeX profesional.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo (JSON)

Genera un CV adaptado en LaTeX.

Reglas:
- Devuelve un documento LaTeX COMPLETO y compilable con `pdflatex`
- Usa `article`, `geometry`, `enumitem`, `hyperref`
- Diseño sobrio, premium, ATS-friendly, una columna
- Máximo 2 páginas
- Incluye: encabezado con contacto real, resumen ejecutivo, experiencia, habilidades, educación, idiomas
- Reordena y enfatiza la experiencia más relevante para la oferta
- Usa keywords reales de la oferta de forma natural
- Debe escribirse en el idioma indicado por `IDIOMA_DOCUMENTO`
- Cada bullet debe sonar a logro profesional concreto, no a descripción genérica
- Prefiere 3-4 bullets fuertes por experiencia, con impacto y contexto
- Si el perfil no cumple algo, reposiciona fortalezas adyacentes en vez de fingir experiencia
- NO inventes información
- Escapa correctamente caracteres de LaTeX
- Si falta un dato de contacto, omítelo
- NO uses placeholders como [Nombre], [Email], [Teléfono], [LinkedIn], [GitHub]
- El CV debe sentirse listo para enviar, no un borrador

Responde SOLO con el código LaTeX, sin fences ni explicaciones."""


CV_MARKDOWN_PROMPT = """Eres un editor senior de CVs técnicos.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo (JSON)

Genera un CV adaptado en Markdown con el mismo contenido del CV final.

Reglas:
- Encabezado con nombre y contacto real
- Resumen profesional ejecutivo de 3-4 líneas
- Experiencia relevante primero
- Habilidades agrupadas inteligentemente, educación e idiomas
- Debe escribirse en el idioma indicado por `IDIOMA_DOCUMENTO`
- Máximo 2 páginas al renderizar
- No inventes información
- NO uses placeholders
- Evita frases vacías como "responsable de" sin impacto
- El documento debe sentirse de nivel senior y listo para enviar

Responde SOLO con el CV en Markdown."""


async def cv_latex_writer_node(state: JoberState) -> dict:
    """Generate the adapted CV using a dedicated LaTeX-first agent."""
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


def _detect_offer_language(state: JoberState) -> str:
    text = " ".join(
        [
            state.oferta.titulo or "",
            state.oferta.descripcion or "",
            " ".join(state.oferta.requisitos or []),
        ]
    ).lower()
    english_markers = [
        "engineer", "machine learning", "remote", "team", "experience", "years",
        "python", "build", "models", "production", "framework", "hiring",
    ]
    score = sum(1 for marker in english_markers if marker in text)
    return "English" if score >= 3 else "Español"

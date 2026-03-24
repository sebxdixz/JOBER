"""CV reader agent: extract text from PDFs and build the master profile."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pypdf import PdfReader

from jober.core.config import get_llm
from jober.core.logging import logger
from jober.core.models import PerfilMaestro
from jober.core.prompts import get_prompt
from jober.core.state import JoberState, view_state
from jober.utils.llm_helpers import ainvoke_with_retry, strip_markdown_fences


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text from a PDF file."""
    reader = PdfReader(str(pdf_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_text_from_cvs(cv_dir: Path) -> str:
    """Concatenate text from all PDFs in a directory."""
    texts: list[str] = []
    for pdf_file in sorted(cv_dir.glob("*.pdf")):
        text = extract_text_from_pdf(pdf_file)
        if text:
            texts.append(f"--- Archivo: {pdf_file.name} ---\n{text}")
    return "\n\n".join(texts)


async def cv_reader_node(state: JoberState) -> dict:
    """LangGraph node that reads CVs and extracts a structured profile."""
    state = view_state(state)
    llm = get_llm()

    cv_text = state.cv_raw_text
    if not cv_text:
        return {"error": "No se encontro texto de CV para analizar."}

    try:
        response = await ainvoke_with_retry(
            llm,
            [
                SystemMessage(content=get_prompt("cv_reader_system")),
                HumanMessage(content=f"Analiza el siguiente CV:\n\n{cv_text}"),
            ],
            operation="cv profile extraction",
        )
    except Exception as exc:
        logger.exception("CV profile extraction failed")
        return {"error": f"No se pudo procesar el CV con el LLM: {exc}"}

    try:
        clean_json = strip_markdown_fences(response.content)
        perfil = PerfilMaestro.model_validate_json(clean_json)
    except Exception:
        logger.exception("Could not parse CV reader payload")
        return {
            "error": f"No se pudo parsear la respuesta del LLM como PerfilMaestro: {response.content[:200]}",
        }

    return {
        "perfil": perfil,
        "current_agent": "cv_reader",
        "next_step": "onboarding",
    }

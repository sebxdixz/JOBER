"""Agente lector de CVs — extrae texto de PDFs y construye el perfil maestro."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pypdf import PdfReader

from jober.core.config import load_settings
from jober.core.models import PerfilMaestro
from jober.core.state import JoberState


SYSTEM_PROMPT = """Eres un experto en recursos humanos y análisis de CVs.
Tu tarea es extraer TODA la información relevante del texto de un CV y devolver un JSON
que siga exactamente el schema de PerfilMaestro.

Extrae:
- nombre, titulo_profesional, resumen
- habilidades_tecnicas (lista de tecnologías, herramientas, lenguajes)
- habilidades_blandas
- experiencias (empresa, cargo, fechas, descripción, tecnologías usadas)
- educacion (institución, título, fechas)
- idiomas
- links (github, linkedin, portfolio, etc.)

Si algún campo no está presente en el CV, déjalo vacío.
Responde SOLO con el JSON válido, sin markdown ni explicaciones."""


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extrae texto plano de un archivo PDF."""
    reader = PdfReader(str(pdf_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_text_from_cvs(cv_dir: Path) -> str:
    """Concatena el texto de todos los PDFs en un directorio."""
    texts: list[str] = []
    for pdf_file in sorted(cv_dir.glob("*.pdf")):
        text = extract_text_from_pdf(pdf_file)
        if text:
            texts.append(f"--- Archivo: {pdf_file.name} ---\n{text}")
    return "\n\n".join(texts)


async def cv_reader_node(state: JoberState) -> dict:
    """Nodo LangGraph: lee CVs y extrae perfil estructurado."""
    settings = load_settings()
    llm = ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
    )

    cv_text = state.cv_raw_text
    if not cv_text:
        return {"error": "No se encontró texto de CV para analizar."}

    response = await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Analiza el siguiente CV:\n\n{cv_text}"),
    ])

    try:
        perfil = PerfilMaestro.model_validate_json(response.content)
    except Exception:
        return {
            "error": f"No se pudo parsear la respuesta del LLM como PerfilMaestro: {response.content[:200]}",
        }

    return {
        "perfil": perfil,
        "current_agent": "cv_reader",
        "next_step": "onboarding",
    }

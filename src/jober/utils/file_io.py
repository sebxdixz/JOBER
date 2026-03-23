"""Utilidades de I/O — guardar perfil, documentos generados, etc."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from jober.core.config import (
    PERFIL_MAESTRO_PATH,
    POSTULACIONES_DIR,
    ensure_jober_dirs,
)
from jober.core.models import (
    DocumentosGenerados,
    OfertaTrabajo,
    PerfilMaestro,
    ResultadoAplicacion,
)
from jober.utils.pdf_export import export_cv_to_pdf, export_cover_letter_to_pdf


def save_perfil_maestro(perfil: PerfilMaestro) -> Path:
    """Guarda el perfil maestro como JSON en ~/.jober/perfil_maestro.json"""
    ensure_jober_dirs()
    PERFIL_MAESTRO_PATH.write_text(
        perfil.model_dump_json(indent=2), encoding="utf-8"
    )
    return PERFIL_MAESTRO_PATH


def load_perfil_maestro() -> PerfilMaestro | None:
    """Carga el perfil maestro desde disco. Retorna None si no existe."""
    if not PERFIL_MAESTRO_PATH.exists():
        return None
    data = PERFIL_MAESTRO_PATH.read_text(encoding="utf-8")
    return PerfilMaestro.model_validate_json(data)


def save_application_output(
    oferta: OfertaTrabajo,
    documentos: DocumentosGenerados,
    resultado_aplicacion: ResultadoAplicacion | None = None,
) -> Path:
    """Guarda los documentos generados (Markdown + PDF) en una carpeta por postulación."""
    ensure_jober_dirs()

    timestamp = datetime.now().strftime("%Y%m%d")
    empresa = oferta.empresa.replace(" ", "_")[:30] if oferta.empresa else "unknown"
    cargo = oferta.titulo.replace(" ", "_")[:30] if oferta.titulo else "job"
    folder_name = f"{timestamp}_{oferta.plataforma}_{empresa}_{cargo}"

    output_dir = POSTULACIONES_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # CV adaptado (Markdown + PDF)
    if documentos.cv_adaptado_md:
        (output_dir / "cv_adaptado.md").write_text(
            documentos.cv_adaptado_md, encoding="utf-8"
        )
        try:
            asyncio.run(
                export_cv_to_pdf(documentos.cv_adaptado_md, output_dir / "cv_adaptado.pdf")
            )
        except RuntimeError:
            # Already inside an event loop (called from async context)
            pass

    # Cover letter (Markdown + PDF)
    if documentos.cover_letter_md:
        (output_dir / "cover_letter.md").write_text(
            documentos.cover_letter_md, encoding="utf-8"
        )
        try:
            asyncio.run(
                export_cover_letter_to_pdf(
                    documentos.cover_letter_md, output_dir / "cover_letter.pdf"
                )
            )
        except RuntimeError:
            pass

    # QA respuestas
    if documentos.qa_respuestas:
        (output_dir / "qa_respuestas.json").write_text(
            json.dumps(documentos.qa_respuestas, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Match analysis
    analysis = {
        "match_score": documentos.match_score,
        "analisis_fit": documentos.analisis_fit,
    }
    (output_dir / "match_analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Oferta original
    (output_dir / "oferta_original.json").write_text(
        oferta.model_dump_json(indent=2), encoding="utf-8"
    )

    if resultado_aplicacion is not None:
        (output_dir / "application_result.json").write_text(
            resultado_aplicacion.model_dump_json(indent=2), encoding="utf-8"
        )

    return output_dir


async def save_application_output_async(
    oferta: OfertaTrabajo,
    documentos: DocumentosGenerados,
    resultado_aplicacion: ResultadoAplicacion | None = None,
) -> Path:
    """Versión async de save_application_output (para uso dentro de jober run)."""
    ensure_jober_dirs()

    timestamp = datetime.now().strftime("%Y%m%d")
    empresa = oferta.empresa.replace(" ", "_")[:30] if oferta.empresa else "unknown"
    cargo = oferta.titulo.replace(" ", "_")[:30] if oferta.titulo else "job"
    folder_name = f"{timestamp}_{oferta.plataforma}_{empresa}_{cargo}"

    output_dir = POSTULACIONES_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # CV adaptado (Markdown + PDF)
    if documentos.cv_adaptado_md:
        (output_dir / "cv_adaptado.md").write_text(
            documentos.cv_adaptado_md, encoding="utf-8"
        )
        try:
            await export_cv_to_pdf(documentos.cv_adaptado_md, output_dir / "cv_adaptado.pdf")
        except Exception:
            pass

    # Cover letter (Markdown + PDF)
    if documentos.cover_letter_md:
        (output_dir / "cover_letter.md").write_text(
            documentos.cover_letter_md, encoding="utf-8"
        )
        try:
            await export_cover_letter_to_pdf(
                documentos.cover_letter_md, output_dir / "cover_letter.pdf"
            )
        except Exception:
            pass

    # QA respuestas
    if documentos.qa_respuestas:
        (output_dir / "qa_respuestas.json").write_text(
            json.dumps(documentos.qa_respuestas, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Match analysis
    analysis = {
        "match_score": documentos.match_score,
        "analisis_fit": documentos.analisis_fit,
    }
    (output_dir / "match_analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Oferta original
    (output_dir / "oferta_original.json").write_text(
        oferta.model_dump_json(indent=2), encoding="utf-8"
    )

    if resultado_aplicacion is not None:
        (output_dir / "application_result.json").write_text(
            resultado_aplicacion.model_dump_json(indent=2), encoding="utf-8"
        )

    return output_dir

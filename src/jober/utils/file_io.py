"""Utilidades de I/O - guardar perfil, documentos generados, etc."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from jober.core.config import ensure_profile_dirs
from jober.core.models import (
    DocumentosGenerados,
    OfertaTrabajo,
    PerfilMaestro,
    ResultadoAplicacion,
)
from jober.utils.pdf_export import (
    export_cover_letter_to_pdf,
    export_cv_to_pdf,
    export_latex_to_pdf_sync,
)


def _safe_fragment(value: str, default: str, max_len: int = 30) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned[:max_len] or default)


def ensure_job_output_dir(
    profile_id: str | None = None,
    oferta: OfertaTrabajo | None = None,
    *,
    url: str = "",
    plataforma: str = "",
    empresa: str = "",
    cargo: str = "",
    timestamp: str | None = None,
) -> Path:
    """Crea una carpeta unica por oferta/intento y devuelve su ruta."""
    paths = ensure_profile_dirs(profile_id)
    job_url = url or (oferta.url if oferta else "")
    platform = plataforma or (oferta.plataforma if oferta else "") or "job"
    company = empresa or (oferta.empresa if oferta else "") or "unknown"
    title = cargo or (oferta.titulo if oferta else "") or "job"
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    url_hash = hashlib.sha1((job_url or f"{platform}:{company}:{title}:{stamp}").encode("utf-8")).hexdigest()[:8]
    folder_name = "_".join([
        stamp,
        _safe_fragment(platform, "job", max_len=16),
        _safe_fragment(company, "unknown"),
        _safe_fragment(title, "job"),
        url_hash,
    ])
    output_dir = paths.postulaciones_dir / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_output_artifact(output_dir: Path, filename: str, payload: dict) -> Path:
    """Guarda un artefacto JSON dentro de una carpeta de postulacion."""
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / filename
    artifact_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact_path


def save_perfil_maestro(perfil: PerfilMaestro, profile_id: str | None = None) -> Path:
    """Guarda el perfil maestro como JSON en ~/.jober/profiles/<id>/perfil_maestro.json"""
    paths = ensure_profile_dirs(profile_id)
    paths.perfil_path.write_text(
        perfil.model_dump_json(indent=2), encoding="utf-8"
    )
    return paths.perfil_path


def load_perfil_maestro(profile_id: str | None = None) -> PerfilMaestro | None:
    """Carga el perfil maestro desde disco. Retorna None si no existe."""
    paths = ensure_profile_dirs(profile_id)
    if not paths.perfil_path.exists():
        return None
    data = paths.perfil_path.read_text(encoding="utf-8")
    return PerfilMaestro.model_validate_json(data)


def save_last_scout(payload: dict, profile_id: str | None = None) -> Path:
    """Guarda el ultimo scouting para reutilizarlo luego."""
    paths = ensure_profile_dirs(profile_id)
    paths.last_scout_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return paths.last_scout_path


def load_last_scout(profile_id: str | None = None) -> dict | None:
    """Carga el ultimo scouting si existe."""
    paths = ensure_profile_dirs(profile_id)
    if not paths.last_scout_path.exists():
        return None
    return json.loads(paths.last_scout_path.read_text(encoding="utf-8"))


def save_application_output(
    oferta: OfertaTrabajo,
    documentos: DocumentosGenerados,
    resultado_aplicacion: ResultadoAplicacion | None = None,
    profile_id: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Guarda los documentos generados (Markdown + PDF) en una carpeta por postulacion."""
    output_dir = output_dir or ensure_job_output_dir(profile_id, oferta)

    # CV adaptado (Markdown + PDF)
    if documentos.cv_adaptado_tex:
        (output_dir / "cv_adaptado.tex").write_text(
            documentos.cv_adaptado_tex, encoding="utf-8"
        )

    if documentos.cv_adaptado_md:
        (output_dir / "cv_adaptado.md").write_text(
            documentos.cv_adaptado_md, encoding="utf-8"
        )
        try:
            compiled = export_latex_to_pdf_sync(
                documentos.cv_adaptado_tex,
                output_dir / "cv_adaptado.pdf",
            )
            if compiled is None:
                asyncio.run(
                    export_cv_to_pdf(documentos.cv_adaptado_md, output_dir / "cv_adaptado.pdf")
                )
        except Exception:
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


async def save_application_output_async(
    oferta: OfertaTrabajo,
    documentos: DocumentosGenerados,
    resultado_aplicacion: ResultadoAplicacion | None = None,
    profile_id: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Version async de save_application_output (para uso dentro de jober run)."""
    output_dir = output_dir or ensure_job_output_dir(profile_id, oferta)

    # CV adaptado (Markdown + PDF)
    if documentos.cv_adaptado_tex:
        (output_dir / "cv_adaptado.tex").write_text(
            documentos.cv_adaptado_tex, encoding="utf-8"
        )

    if documentos.cv_adaptado_md:
        (output_dir / "cv_adaptado.md").write_text(
            documentos.cv_adaptado_md, encoding="utf-8"
        )
        try:
            compiled = export_latex_to_pdf_sync(
                documentos.cv_adaptado_tex,
                output_dir / "cv_adaptado.pdf",
            )
            if compiled is None:
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

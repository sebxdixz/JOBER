"""Local language detection helpers for job offers."""

from __future__ import annotations

import re

from langdetect import DetectorFactory, detect

from jober.core.models import OfertaTrabajo


DetectorFactory.seed = 0


def detect_offer_document_language(oferta: OfertaTrabajo) -> str:
    """Detect whether the offer should generate documents in English or Spanish."""
    sample = "\n".join(
        part.strip()
        for part in [
            oferta.descripcion or "",
            " ".join(oferta.requisitos or []),
            oferta.titulo or "",
        ]
        if part and part.strip()
    )
    sample = re.sub(r"\s+", " ", sample).strip()
    if len(sample) < 40:
        return "Espanol"

    try:
        lang = detect(sample)
    except Exception:
        return "Espanol"

    return "English" if lang == "en" else "Espanol"

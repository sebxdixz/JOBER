"""Utilidades de tracking — lectura/escritura del CSV de postulaciones."""

from __future__ import annotations

import csv
from pathlib import Path

from jober.core.config import TRACKING_CSV
from jober.core.models import RegistroPostulacion


HEADERS = [
    "fecha", "empresa", "cargo", "plataforma", "url",
    "estado", "carpeta_output", "notas",
]


def _ensure_csv() -> None:
    """Crea el CSV con headers si no existe."""
    if not TRACKING_CSV.exists():
        TRACKING_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKING_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)


def add_record(record: RegistroPostulacion) -> None:
    """Agrega un registro de postulación al CSV."""
    _ensure_csv()
    with open(TRACKING_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            record.fecha,
            record.empresa,
            record.cargo,
            record.plataforma,
            record.url,
            record.estado.value,
            record.carpeta_output,
            record.notas,
        ])


def read_all_records() -> list[RegistroPostulacion]:
    """Lee todos los registros del CSV."""
    _ensure_csv()
    records: list[RegistroPostulacion] = []
    with open(TRACKING_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(RegistroPostulacion(**row))
    return records


def get_stats() -> dict:
    """Devuelve estadísticas básicas de las postulaciones."""
    records = read_all_records()
    total = len(records)
    by_status: dict[str, int] = {}
    by_platform: dict[str, int] = {}

    for r in records:
        by_status[r.estado.value] = by_status.get(r.estado.value, 0) + 1
        if r.plataforma:
            by_platform[r.plataforma] = by_platform.get(r.plataforma, 0) + 1

    return {
        "total": total,
        "por_estado": by_status,
        "por_plataforma": by_platform,
    }

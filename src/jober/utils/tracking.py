"""Utilidades de tracking - lectura/escritura del CSV de postulaciones."""

from __future__ import annotations

import csv

from jober.core.config import ensure_profile_dirs
from jober.core.models import RegistroPostulacion


HEADERS = [
    "fecha", "empresa", "cargo", "plataforma", "url",
    "estado", "carpeta_output", "notas",
]


def _ensure_csv(profile_id: str | None = None):
    """Crea el CSV con headers si no existe."""
    paths = ensure_profile_dirs(profile_id)
    if not paths.tracking_csv.exists():
        paths.tracking_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(paths.tracking_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
    return paths.tracking_csv


def add_record(record: RegistroPostulacion, profile_id: str | None = None) -> None:
    """Agrega un registro de postulacion al CSV."""
    tracking_csv = _ensure_csv(profile_id)
    with open(tracking_csv, "a", newline="", encoding="utf-8") as f:
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


def read_all_records(profile_id: str | None = None) -> list[RegistroPostulacion]:
    """Lee todos los registros del CSV."""
    tracking_csv = _ensure_csv(profile_id)
    records: list[RegistroPostulacion] = []
    with open(tracking_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(RegistroPostulacion(**row))
    return records


def get_stats(profile_id: str | None = None) -> dict:
    """Devuelve estadisticas basicas de las postulaciones."""
    records = read_all_records(profile_id)
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

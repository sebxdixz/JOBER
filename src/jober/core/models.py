"""Modelos Pydantic compartidos por todos los agentes."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Perfil Maestro ──────────────────────────────────────────────────────────

class Experiencia(BaseModel):
    empresa: str = ""
    cargo: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = "Presente"
    descripcion: str = ""
    tecnologias: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: dict) -> dict:
        if isinstance(data, dict):
            # LLM a veces devuelve "fechas" en vez de fecha_inicio/fecha_fin
            if "fechas" in data and "fecha_inicio" not in data:
                fechas = data.pop("fechas", "")
                parts = [p.strip() for p in fechas.replace("–", "-").split("-", 1)]
                data["fecha_inicio"] = parts[0] if parts else ""
                data["fecha_fin"] = parts[1] if len(parts) > 1 else "Presente"
        return data


class Educacion(BaseModel):
    institucion: str = ""
    titulo: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "fechas" in data and "fecha_inicio" not in data:
                fechas = data.pop("fechas", "")
                parts = [p.strip() for p in fechas.replace("–", "-").split("-", 1)]
                data["fecha_inicio"] = parts[0] if parts else ""
                data["fecha_fin"] = parts[1] if len(parts) > 1 else ""
        return data


class PerfilMaestro(BaseModel):
    nombre: str = ""
    titulo_profesional: str = ""
    resumen: str = ""
    habilidades_tecnicas: list[str] = Field(default_factory=list)
    habilidades_blandas: list[str] = Field(default_factory=list)
    experiencias: list[Experiencia] = Field(default_factory=list)
    educacion: list[Educacion] = Field(default_factory=list)
    idiomas: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: dict) -> dict:
        if isinstance(data, dict):
            # LLM a veces devuelve idiomas como string vacío
            idiomas = data.get("idiomas", [])
            if isinstance(idiomas, str):
                data["idiomas"] = [i.strip() for i in idiomas.split(",") if i.strip()] if idiomas else []
            # LLM a veces devuelve links como lista de {tipo, url} en vez de dict
            links = data.get("links", {})
            if isinstance(links, list):
                data["links"] = {
                    item.get("tipo", item.get("name", f"link_{i}")): item.get("url", "")
                    for i, item in enumerate(links)
                    if isinstance(item, dict)
                }
        return data


# ── Oferta de Trabajo ───────────────────────────────────────────────────────

class OfertaTrabajo(BaseModel):
    url: str = ""
    titulo: str = ""
    empresa: str = ""
    ubicacion: str = ""
    modalidad: str = ""  # remoto, hibrido, presencial
    descripcion: str = ""
    requisitos: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    salario: str = ""
    plataforma: str = ""  # getonbrd, meetfrank, linkedin
    fecha_scraping: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── Tracking ────────────────────────────────────────────────────────────────

class EstadoPostulacion(str, Enum):
    PENDIENTE = "pendiente"
    APLICADO = "aplicado"
    ENTREVISTA = "entrevista"
    RECHAZADO = "rechazado"
    OFERTA = "oferta"


class RegistroPostulacion(BaseModel):
    fecha: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    empresa: str = ""
    cargo: str = ""
    plataforma: str = ""
    url: str = ""
    estado: EstadoPostulacion = EstadoPostulacion.APLICADO
    carpeta_output: str = ""
    notas: str = ""


# ── Documentos Generados ───────────────────────────────────────────────────

class DocumentosGenerados(BaseModel):
    cv_adaptado_md: str = ""
    cover_letter_md: str = ""
    qa_respuestas: dict[str, str] = Field(default_factory=dict)
    match_score: float = 0.0
    analisis_fit: str = ""

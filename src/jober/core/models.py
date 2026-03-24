"""Modelos Pydantic compartidos por todos los agentes."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

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


class PreferenciasLaborales(BaseModel):
    """Preferencias del usuario para búsqueda autónoma de trabajo."""

    # ── Identidad profesional ──────────────────────────────────────────────
    roles_deseados: list[str] = Field(default_factory=list)
    nivel_experiencia: str = ""  # junior, mid, senior, lead, etc.
    anos_experiencia: int = 0
    resumen_candidato: str = ""  # Frase corta que resume quién es profesionalmente

    # ── Habilidades ────────────────────────────────────────────────────────
    habilidades_dominadas: list[str] = Field(default_factory=list)  # Las que domina bien
    habilidades_en_aprendizaje: list[str] = Field(default_factory=list)  # Aprendiendo / básicas
    habilidades_must_have: list[str] = Field(default_factory=list)  # Críticas para él
    habilidades_nice_to_have: list[str] = Field(default_factory=list)
    herramientas_y_tecnologias: list[str] = Field(default_factory=list)  # Stack concreto

    # ── Preferencias de búsqueda ────────────────────────────────────────────
    industrias_preferidas: list[str] = Field(default_factory=list)
    tipo_empresa: list[str] = Field(default_factory=list)  # startup, corporativo, pyme, etc.
    modalidad: List[str] = Field(default_factory=lambda: ["remoto", "hibrido", "presencial"])
    ubicaciones: List[str] = Field(default_factory=list)
    paises_permitidos: List[str] = Field(default_factory=list)  # ["Chile", "Argentina", "Remote"]
    paises_excluidos: List[str] = Field(default_factory=list)  # ["Estados Unidos", "USA"]
    disponibilidad: str = "inmediata"  # inmediata, 2 semanas, 1 mes, etc.
    jornada: str = "full-time"  # full-time, part-time, freelance, contrato

    # ── Expectativas salariales ────────────────────────────────────────────
    salario_minimo: str = ""  # ej: "$800.000 CLP", "$2000 USD"
    salario_ideal: str = ""
    moneda_preferida: str = ""
    acepta_negociar_salario: bool = True

    # ── Tolerancia y estrategia ────────────────────────────────────────────
    min_match_score: float = 0.55  # Aplica si match >= 55%
    aplicar_sin_100_requisitos: bool = True
    max_anos_experiencia_extra: int = 2  # Aplica a puestos que pidan hasta 2 años más
    abierto_a_roles_similares: bool = True  # Si busca "Data Scientist" también aplica a "ML Engineer"

    # ── Deal breakers ──────────────────────────────────────────────────────
    deal_breakers: list[str] = Field(default_factory=list)  # ej: ["presencial obligatorio", "viajes frecuentes"]
    idiomas_requeridos: list[str] = Field(default_factory=list)  # Idiomas que domina para el trabajo

    # ── Motivación y contexto ───────────────────────────────────────────────
    motivacion: str = ""  # Por qué busca trabajo (crecer, cambiar rubro, primer empleo, etc.)
    fortalezas_clave: list[str] = Field(default_factory=list)  # Lo que el usuario cree que lo diferencia
    areas_mejora: list[str] = Field(default_factory=list)  # Lo que reconoce que le falta

    # ── Plataformas y ritmo ────────────────────────────────────────────────
    plataformas_activas: list[str] = Field(default_factory=lambda: ["getonbrd", "linkedin", "meetfrank"])
    max_aplicaciones_por_dia: int = 10
    delay_entre_aplicaciones_segundos: int = 60


class PerfilMaestro(BaseModel):
    nombre: str = ""
    email: str = ""
    telefono: str = ""
    ubicacion_actual: str = ""
    titulo_profesional: str = ""
    resumen: str = ""
    habilidades_tecnicas: list[str] = Field(default_factory=list)
    habilidades_blandas: list[str] = Field(default_factory=list)
    experiencias: list[Experiencia] = Field(default_factory=list)
    educacion: list[Educacion] = Field(default_factory=list)
    idiomas: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    
    # Preferencias de búsqueda autónoma
    preferencias: PreferenciasLaborales = Field(default_factory=PreferenciasLaborales)

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


class JobLead(BaseModel):
    """Lead liviano obtenido desde buscadores/APIs antes del scraping profundo."""

    url: str = ""
    titulo: str = ""
    empresa: str = ""
    ubicacion: str = ""
    plataforma: str = ""
    snippet: str = ""
    source: str = ""

# ── Tracking ────────────────────────────────────────────────────────────────

class EstadoPostulacion(str, Enum):
    PREPARADO = "preparado"
    PENDIENTE = "pendiente"
    APLICADO = "aplicado"
    FALLIDO = "fallido"
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
    cv_adaptado_tex: str = ""
    cv_adaptado_md: str = ""
    cover_letter_md: str = ""
    qa_respuestas: dict[str, str] = Field(default_factory=dict)
    match_score: float = 0.0
    analisis_fit: str = ""


class ResultadoAplicacion(BaseModel):
    enviado: bool = False
    metodo: str = ""
    plataforma: str = ""
    url_final: str = ""
    mensaje: str = ""
    detalles: dict[str, str] = Field(default_factory=dict)

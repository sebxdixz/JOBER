"""Configuración global de Jober. Lee desde ~/.jober/.env"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


JOBER_HOME = Path.home() / ".jober"
JOBER_ENV_FILE = JOBER_HOME / ".env"
CV_BASE_DIR = JOBER_HOME / "cv_base"
POSTULACIONES_DIR = JOBER_HOME / "postulaciones"
TRACKING_CSV = JOBER_HOME / "tracking_postulaciones.csv"
PERFIL_MAESTRO_PATH = JOBER_HOME / "perfil_maestro.json"


def ensure_jober_dirs() -> None:
    """Crea las carpetas base de ~/.jober/ si no existen."""
    for d in [JOBER_HOME, CV_BASE_DIR, POSTULACIONES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Settings cargadas desde ~/.jober/.env"""

    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.2

    class Config:
        env_file = str(JOBER_ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


def load_settings() -> Settings:
    """Carga settings; si no existe .env, devuelve defaults vacíos."""
    if JOBER_ENV_FILE.exists():
        return Settings()
    return Settings()

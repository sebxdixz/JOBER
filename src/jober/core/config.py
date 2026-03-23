"""Configuración global de Jober. Lee desde ~/.jober/.env"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings


JOBER_HOME = Path(os.getenv("JOBER_HOME", str(Path.home() / ".jober"))).expanduser()
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

    llm_api_key: str = ""
    llm_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    llm_model: str = "GLM-4.7-flash"
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


def get_llm(temperature: float | None = None) -> ChatOpenAI:
    """Crea una instancia de ChatOpenAI apuntando al provider configurado (Z.AI por defecto)."""
    settings = load_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

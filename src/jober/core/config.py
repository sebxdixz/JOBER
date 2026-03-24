"""Configuracion global de Jober. Lee desde ~/.jober/.env"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings


JOBER_HOME = Path(os.getenv("JOBER_HOME", str(Path.home() / ".jober"))).expanduser()
JOBER_ENV_FILE = JOBER_HOME / ".env"
PROFILES_DIR = JOBER_HOME / "profiles"
ACTIVE_PROFILE_PATH = JOBER_HOME / "active_profile.json"
DEFAULT_PROFILE_ID = "default"

# Legacy (pre multi-profile) paths
CV_BASE_DIR = JOBER_HOME / "cv_base"
POSTULACIONES_DIR = JOBER_HOME / "postulaciones"
TRACKING_CSV = JOBER_HOME / "tracking_postulaciones.csv"
PERFIL_MAESTRO_PATH = JOBER_HOME / "perfil_maestro.json"
LAST_SCOUT_PATH = JOBER_HOME / "last_scout.json"

PROFILE_FILE_NAME = "perfil_maestro.json"
CV_DIR_NAME = "cv_base"
POSTULACIONES_DIR_NAME = "postulaciones"
TRACKING_FILE_NAME = "tracking_postulaciones.csv"
LAST_SCOUT_FILE_NAME = "last_scout.json"


@dataclass(frozen=True)
class ProfilePaths:
    profile_id: str
    profile_dir: Path
    perfil_path: Path
    cv_base_dir: Path
    postulaciones_dir: Path
    tracking_csv: Path
    last_scout_path: Path


def normalize_profile_id(profile_id: str | None) -> str:
    if not profile_id:
        return DEFAULT_PROFILE_ID
    cleaned = profile_id.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", cleaned)
    cleaned = cleaned.strip("-_")
    return cleaned or DEFAULT_PROFILE_ID


def get_active_profile_id() -> str:
    if ACTIVE_PROFILE_PATH.exists():
        raw = ACTIVE_PROFILE_PATH.read_text(encoding="utf-8").strip()
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("active_profile"):
                return normalize_profile_id(str(payload["active_profile"]))
        except json.JSONDecodeError:
            if raw:
                return normalize_profile_id(raw)
    return DEFAULT_PROFILE_ID


def set_active_profile_id(profile_id: str) -> str:
    profile_id = normalize_profile_id(profile_id)
    JOBER_HOME.mkdir(parents=True, exist_ok=True)
    ACTIVE_PROFILE_PATH.write_text(
        json.dumps({"active_profile": profile_id}, indent=2),
        encoding="utf-8",
    )
    return profile_id


def list_profile_ids() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    ids: list[str] = []
    for entry in PROFILES_DIR.iterdir():
        if entry.is_dir():
            ids.append(entry.name)
    return sorted(ids)


def _build_profile_paths(profile_id: str) -> ProfilePaths:
    profile_dir = PROFILES_DIR / profile_id
    return ProfilePaths(
        profile_id=profile_id,
        profile_dir=profile_dir,
        perfil_path=profile_dir / PROFILE_FILE_NAME,
        cv_base_dir=profile_dir / CV_DIR_NAME,
        postulaciones_dir=profile_dir / POSTULACIONES_DIR_NAME,
        tracking_csv=profile_dir / TRACKING_FILE_NAME,
        last_scout_path=profile_dir / LAST_SCOUT_FILE_NAME,
    )


def _maybe_migrate_legacy_profile(profile_id: str, paths: ProfilePaths) -> None:
    if profile_id != DEFAULT_PROFILE_ID:
        return

    legacy_exists = any(
        p.exists()
        for p in [
            PERFIL_MAESTRO_PATH,
            CV_BASE_DIR,
            TRACKING_CSV,
            LAST_SCOUT_PATH,
        ]
    )
    if not legacy_exists:
        return

    if PERFIL_MAESTRO_PATH.exists() and not paths.perfil_path.exists():
        try:
            shutil.copy2(PERFIL_MAESTRO_PATH, paths.perfil_path)
        except OSError:
            pass

    if CV_BASE_DIR.exists():
        pdfs = list(CV_BASE_DIR.glob("*.pdf"))
        if pdfs and not any(paths.cv_base_dir.glob("*.pdf")):
            for pdf in pdfs:
                dest = paths.cv_base_dir / pdf.name
                if not dest.exists():
                    try:
                        shutil.copy2(pdf, dest)
                    except OSError:
                        pass

    if TRACKING_CSV.exists() and not paths.tracking_csv.exists():
        try:
            shutil.copy2(TRACKING_CSV, paths.tracking_csv)
        except OSError:
            pass

    if LAST_SCOUT_PATH.exists() and not paths.last_scout_path.exists():
        try:
            shutil.copy2(LAST_SCOUT_PATH, paths.last_scout_path)
        except OSError:
            pass


def resolve_profile_id(profile_id: str | None = None) -> str:
    if profile_id:
        return normalize_profile_id(profile_id)
    return get_active_profile_id()


def ensure_profile_dirs(profile_id: str | None = None) -> ProfilePaths:
    profile_id = resolve_profile_id(profile_id)
    JOBER_HOME.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    paths = _build_profile_paths(profile_id)
    paths.profile_dir.mkdir(parents=True, exist_ok=True)
    paths.cv_base_dir.mkdir(parents=True, exist_ok=True)
    paths.postulaciones_dir.mkdir(parents=True, exist_ok=True)

    _maybe_migrate_legacy_profile(profile_id, paths)
    return paths


def ensure_jober_dirs() -> None:
    """Crea las carpetas base de ~/.jober/ si no existen."""
    ensure_profile_dirs()


class Settings(BaseSettings):
    """Settings cargadas desde ~/.jober/.env"""

    llm_api_key: str = ""
    llm_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    llm_model: str = "GLM-4.7-flash"
    llm_temperature: float = 0.2
    vision_api_key: str = ""
    vision_base_url: str = ""
    vision_model: str = ""
    vision_temperature: float = 0.0

    class Config:
        env_file = str(JOBER_ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


def load_settings() -> Settings:
    """Carga settings; si no existe .env, devuelve defaults vacios."""
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


def get_vision_llm(temperature: float | None = None) -> ChatOpenAI:
    """Crea una instancia OpenAI-compatible para modelos multimodales."""
    settings = load_settings()
    return ChatOpenAI(
        model=settings.vision_model or settings.llm_model,
        temperature=temperature if temperature is not None else settings.vision_temperature,
        api_key=settings.vision_api_key or settings.llm_api_key,
        base_url=settings.vision_base_url or settings.llm_base_url,
    )

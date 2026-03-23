from __future__ import annotations

import importlib
import os
import shutil
from pathlib import Path
import uuid

from jober.core.models import PerfilMaestro


def _make_tmp_dir() -> Path:
    candidates = [
        os.getenv("JOBER_TEST_BASE", ""),
        str(Path.home() / ".codex" / "memories" / "jober_test_tmp"),
        str(Path.home() / "jober_test_tmp"),
        str(Path.cwd() / ".jober_test_tmp"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        base = Path(candidate)
        try:
            base.mkdir(parents=True, exist_ok=True)
            tmp_dir = base / f"tmp_{uuid.uuid4().hex}"
            tmp_dir.mkdir(parents=True, exist_ok=False)
            return tmp_dir
        except Exception:
            continue
    fallback = Path.cwd() / f".jober_test_tmp_{uuid.uuid4().hex}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _reload(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOBER_HOME", str(tmp_path))
    import jober.core.config as config
    importlib.reload(config)
    import jober.utils.file_io as file_io
    importlib.reload(file_io)
    import jober.utils.tracking as tracking
    importlib.reload(tracking)
    return config, file_io, tracking


def test_profile_paths_and_active(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        config, _, _ = _reload(monkeypatch, tmp_path)
        paths = config.ensure_profile_dirs("demo-profile")

        assert paths.profile_dir.exists()
        assert paths.cv_base_dir.exists()
        assert paths.postulaciones_dir.exists()

        active = config.set_active_profile_id("Demo Profile")
        assert active == "demo-profile"
        assert config.get_active_profile_id() == "demo-profile"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_legacy_migration(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        config, file_io, _ = _reload(monkeypatch, tmp_path)

        config.JOBER_HOME.mkdir(parents=True, exist_ok=True)
        config.PERFIL_MAESTRO_PATH.write_text('{"nombre": "Legacy"}', encoding="utf-8")
        config.CV_BASE_DIR.mkdir(parents=True, exist_ok=True)
        (config.CV_BASE_DIR / "cv.pdf").write_bytes(b"%PDF-1.4")
        config.TRACKING_CSV.write_text(
            "fecha,empresa,cargo,plataforma,url,estado,carpeta_output,notas\n",
            encoding="utf-8",
        )
        config.LAST_SCOUT_PATH.write_text('{"candidates": []}', encoding="utf-8")

        paths = config.ensure_profile_dirs()
        assert paths.perfil_path.exists()
        assert paths.last_scout_path.exists()
        assert any(paths.cv_base_dir.glob("*.pdf"))

        perfil = file_io.load_perfil_maestro()
        assert perfil is not None
        assert perfil.nombre == "Legacy"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_save_and_load_profile(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, file_io, _ = _reload(monkeypatch, tmp_path)
        perfil = PerfilMaestro(nombre="Test User", email="test@example.com")
        file_io.save_perfil_maestro(perfil, "ai")

        loaded = file_io.load_perfil_maestro("ai")
        assert loaded is not None
        assert loaded.nombre == "Test User"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_last_scout(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, file_io, _ = _reload(monkeypatch, tmp_path)
        payload = {"generated_at": "now", "candidates": [{"url": "https://example.com"}]}
        file_io.save_last_scout(payload, "ai")
        loaded = file_io.load_last_scout("ai")

        assert loaded is not None
        assert loaded["candidates"][0]["url"] == "https://example.com"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

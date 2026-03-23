from __future__ import annotations

import importlib
import os
import shutil
from pathlib import Path
import uuid

from jober.core.models import EstadoPostulacion, RegistroPostulacion


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
    import jober.utils.tracking as tracking
    importlib.reload(tracking)
    return config, tracking


def test_tracking_stats(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, tracking = _reload(monkeypatch, tmp_path)

        record = RegistroPostulacion(
            empresa="Acme",
            cargo="ML Engineer",
            plataforma="linkedin",
            url="https://example.com",
            estado=EstadoPostulacion.APLICADO,
            carpeta_output="out",
            notas="ok",
        )
        tracking.add_record(record, "ai")
        stats = tracking.get_stats("ai")

        assert stats["total"] == 1
        assert stats["por_estado"]["aplicado"] == 1
        assert stats["por_plataforma"]["linkedin"] == 1
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

from __future__ import annotations

import importlib
import os
import shutil
from pathlib import Path
import uuid

from typer.testing import CliRunner

from jober.core.models import DocumentosGenerados, OfertaTrabajo, PerfilMaestro, ResultadoAplicacion


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
    import jober.cli.main as main
    importlib.reload(main)
    return config, file_io, tracking, main


def test_profile_paths_and_active(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        config, _, _, _ = _reload(monkeypatch, tmp_path)
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
        config, file_io, _, _ = _reload(monkeypatch, tmp_path)

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
        _, file_io, _, _ = _reload(monkeypatch, tmp_path)
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
        _, file_io, _, _ = _reload(monkeypatch, tmp_path)
        payload = {"generated_at": "now", "candidates": [{"url": "https://example.com"}]}
        file_io.save_last_scout(payload, "ai")
        loaded = file_io.load_last_scout("ai")

        assert loaded is not None
        assert loaded["candidates"][0]["url"] == "https://example.com"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_profile_create_prompts_for_missing_id(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        config, _, _, main = _reload(monkeypatch, tmp_path)
        runner = CliRunner()

        result = runner.invoke(main.app, ["profile", "create"], input="data\n")

        assert result.exit_code == 0
        assert "Perfil creado: data" in result.stdout
        assert (tmp_path / "profiles" / "data").exists()
        assert config.get_active_profile_id() == "data"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_profile_help_shows_examples(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, _, _, main = _reload(monkeypatch, tmp_path)
        runner = CliRunner()

        result = runner.invoke(main.app, ["profile", "--help"])

        assert result.exit_code == 0
        assert "jober profile create data" in result.stdout
        assert "jober profile use data" in result.stdout
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_application_output_reuses_existing_output_dir(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, file_io, _, _ = _reload(monkeypatch, tmp_path)
        oferta = OfertaTrabajo(
            url="https://example.com/jobs/123",
            titulo="AI Engineer",
            empresa="Acme",
            ubicacion="Remote",
            modalidad="remoto",
            plataforma="linkedin",
        )
        docs = DocumentosGenerados(
            cv_adaptado_tex="\\documentclass{article}\\begin{document}CV\\end{document}",
            cv_adaptado_md="# CV",
            cover_letter_md="# Cover",
            match_score=0.9,
            analisis_fit="Buen match",
        )
        output_dir = file_io.ensure_job_output_dir("ai", oferta, timestamp="20260323_230000")

        first_dir = file_io.save_application_output(oferta, docs, profile_id="ai", output_dir=output_dir)
        second_dir = file_io.save_application_output(
            oferta,
            docs,
            ResultadoAplicacion(enviado=False, mensaje="Preparado"),
            profile_id="ai",
            output_dir=output_dir,
        )

        assert first_dir == output_dir
        assert second_dir == output_dir
        assert (output_dir / "cv_adaptado.md").exists()
        assert (output_dir / "application_result.json").exists()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_write_output_artifact_creates_physical_trace(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, file_io, _, _ = _reload(monkeypatch, tmp_path)
        output_dir = file_io.ensure_job_output_dir(
            "ai",
            url="https://example.com/jobs/trace",
            plataforma="linkedin",
            empresa="Trace Co",
            cargo="ML Engineer",
            timestamp="20260323_231500",
        )

        artifact = file_io.write_output_artifact(output_dir, "screening_result.json", {
            "status": "filtered",
            "notes": ["Solo remoto: la oferta no parece remota."],
        })

        assert artifact.exists()
        assert "Solo remoto" in artifact.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_status_server_renders_output_dir_and_artifacts(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        monkeypatch.setenv("JOBER_HOME", str(tmp_path))
        import jober.core.config as config
        importlib.reload(config)
        import jober.utils.file_io as file_io
        importlib.reload(file_io)
        import jober.utils.runtime_status as runtime_status
        importlib.reload(runtime_status)
        import jober.utils.status_server as status_server
        importlib.reload(status_server)

        output_dir = file_io.ensure_job_output_dir(
            "ai",
            url="https://example.com/jobs/status",
            plataforma="linkedin",
            empresa="Trace Co",
            cargo="AI Engineer",
            timestamp="20260324_100000",
        )
        file_io.write_output_artifact(output_dir, "screening_result.json", {
            "status": "filtered",
            "notes": ["Solo remoto: la oferta no parece remota."],
        })

        runtime_status.update_status(
            "ai",
            mode="run",
            stage="prefilter",
            message="Probando UI",
            jobs=[{
                "url": "https://example.com/jobs/status",
                "title": "AI Engineer",
                "company": "Trace Co",
                "location": "Remote",
                "platform": "linkedin",
                "status": "filtered",
                "output_dir": str(output_dir),
            }],
        )
        status = runtime_status.load_status("ai")
        html = status_server._render_dashboard(status)

        assert "screening_result.json" in html
        assert str(output_dir) in html

        artifact_path, content, error = status_server._load_artifact(
            "ai",
            status,
            "https://example.com/jobs/status",
            "screening_result.json",
        )
        assert error == ""
        assert artifact_path is not None
        assert content is not None
        assert b"filtered" in content
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_run_warm_start_loads_last_scout(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        monkeypatch.setenv("JOBER_HOME", str(tmp_path))
        import jober.core.config as config
        importlib.reload(config)
        import jober.utils.file_io as file_io
        importlib.reload(file_io)
        import jober.cli.autonomous as autonomous
        importlib.reload(autonomous)

        file_io.save_last_scout({
            "generated_at": "now",
            "candidates": [
                {
                    "url": "https://example.com/jobs/1",
                    "cargo": "AI Engineer",
                    "empresa": "Acme",
                    "ubicacion": "Remote",
                    "plataforma": "linkedin",
                    "source": "last_scout",
                    "snippet": "AI role",
                },
                {
                    "url": "https://example.com/jobs/1",
                    "cargo": "Duplicate",
                },
                {
                    "url": "https://example.com/jobs/2",
                    "cargo": "ML Engineer",
                    "empresa": "Beta",
                    "ubicacion": "Remote",
                    "plataforma": "getonbrd",
                },
            ],
        }, "ai")

        leads = autonomous._load_warm_start_leads("ai", 3)

        assert len(leads) == 2
        assert leads[0].titulo == "AI Engineer"
        assert leads[0].source == "last_scout"
        assert leads[1].plataforma == "getonbrd"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

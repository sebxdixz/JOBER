from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from tenacity import wait_fixed


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


def _reload_logging_stack(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOBER_HOME", str(tmp_path))
    import jober.core.config as config
    importlib.reload(config)
    import jober.core.logging as logging_mod
    importlib.reload(logging_mod)
    import jober.core.prompts as prompts_mod
    importlib.reload(prompts_mod)
    import jober.utils.llm_helpers as llm_helpers
    importlib.reload(llm_helpers)
    return logging_mod, prompts_mod, llm_helpers


def test_export_latex_to_pdf_sync_returns_none_on_timeout(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        import jober.utils.pdf_export as pdf_export

        monkeypatch.setattr(pdf_export.shutil, "which", lambda _: "pdflatex")

        class _FakeTempDir:
            def __init__(self, path: Path):
                self.path = path

            def __enter__(self):
                self.path.mkdir(parents=True, exist_ok=True)
                return str(self.path)

            def __exit__(self, exc_type, exc, tb):
                shutil.rmtree(self.path, ignore_errors=True)
                return False

        monkeypatch.setattr(
            pdf_export.tempfile,
            "TemporaryDirectory",
            lambda: _FakeTempDir(tmp_path / "latex_tmp"),
        )

        def _timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

        monkeypatch.setattr(pdf_export.subprocess, "run", _timeout)

        result = pdf_export.export_latex_to_pdf_sync(
            "\\documentclass{article}\\begin{document}hola\\end{document}",
            tmp_path / "cv.pdf",
        )

        assert result is None
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.asyncio
async def test_ainvoke_with_retry_retries_rate_limits(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, _, llm_helpers = _reload_logging_stack(monkeypatch, tmp_path)

        class FakeLLM:
            def __init__(self):
                self.calls = 0

            async def ainvoke(self, messages):
                self.calls += 1
                if self.calls < 3:
                    raise RuntimeError("429 rate limit")
                return SimpleNamespace(content="ok")

        llm = FakeLLM()
        response = await llm_helpers.ainvoke_with_retry(
            llm,
            [SimpleNamespace(content="hello")],
            operation="test retry",
            max_attempts=3,
            wait_strategy=wait_fixed(0),
        )

        assert response.content == "ok"
        assert llm.calls == 3
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_logger_writes_to_jober_log(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        logging_mod, _, _ = _reload_logging_stack(monkeypatch, tmp_path)

        logging_mod.logger.info("stability log smoke test")

        assert logging_mod.LOG_FILE.exists()
        assert "stability log smoke test" in logging_mod.LOG_FILE.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_prompt_override_from_local_markdown(monkeypatch):
    tmp_path = _make_tmp_dir()
    try:
        _, prompts_mod, _ = _reload_logging_stack(monkeypatch, tmp_path)

        override_path = prompts_mod.prompt_override_path("cv_reader_system")
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text("PROMPT OVERRIDE TEST", encoding="utf-8")

        assert prompts_mod.get_prompt("cv_reader_system") == "PROMPT OVERRIDE TEST"
        assert prompts_mod.PROMPTS_README.exists()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_typed_state_helpers_coerce_nested_models():
    from jober.core.models import DocumentosGenerados, OfertaTrabajo, PerfilMaestro
    from jober.core.state import JoberState, coerce_state, new_state, view_state

    raw: JoberState = {
        "perfil": {"nombre": "Test User"},
        "oferta": {"titulo": "AI Engineer", "empresa": "Acme"},
        "documentos": {"match_score": 0.75},
    }

    coerced = coerce_state(raw)
    assert isinstance(coerced["perfil"], PerfilMaestro)
    assert isinstance(coerced["oferta"], OfertaTrabajo)
    assert isinstance(coerced["documentos"], DocumentosGenerados)

    state = view_state(raw)
    assert state.perfil.nombre == "Test User"
    assert state.oferta.titulo == "AI Engineer"
    assert state.documentos.match_score == 0.75

    fresh = new_state()
    assert isinstance(fresh["perfil"], PerfilMaestro)
    assert fresh["messages"] == []


def test_evaluate_offer_requires_exact_must_have_match():
    from jober.agents.offer_evaluator import evaluate_offer
    from jober.core.models import OfertaTrabajo, PerfilMaestro

    perfil = PerfilMaestro(nombre="Test Candidate")
    perfil.preferencias.roles_deseados = ["AI Engineer"]
    perfil.preferencias.habilidades_must_have = ["AI"]
    perfil.preferencias.aplicar_sin_100_requisitos = False
    perfil.preferencias.modalidad = ["remote"]
    perfil.preferencias.paises_permitidos = ["remote"]

    oferta = OfertaTrabajo(
        titulo="AI Engineer",
        modalidad="remote",
        ubicacion="Remote",
        descripcion="Please send your email details to continue with the process.",
    )

    should_apply, notes, _score = evaluate_offer(oferta, perfil)

    assert should_apply is False
    assert all("Must-have detectadas" not in note for note in notes)
    assert any("must-have" in note.lower() for note in notes)


def test_detect_offer_document_language_handles_spanglish_offer():
    from jober.core.models import OfertaTrabajo
    from jober.utils.language_detection import detect_offer_document_language

    oferta = OfertaTrabajo(
        titulo="AI Engineer remoto",
        descripcion=(
            "Buscamos un engineer para nuestro team remoto en Chile. "
            "Trabajaras con datos, clientes y producto. "
            "Necesitamos experiencia en Python, comunicacion en espanol y colaboracion con equipos locales. "
            "El rol participara en reuniones con operaciones y apoyo comercial."
        ),
    )

    assert detect_offer_document_language(oferta) == "Espanol"


def test_extract_jobposting_json_ld_prefers_structured_schema():
    from jober.agents.job_scraper import extract_jobposting_json_ld

    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "AI Engineer",
        "description": "<p>Build LLM products for remote teams.</p>",
        "hiringOrganization": {"@type": "Organization", "name": "Acme AI"},
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {
            "@type": "Country",
            "name": "Chile",
        },
        "qualifications": ["Python", "LLM systems", "3 years of experience"],
        "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "USD",
            "value": {"@type": "QuantitativeValue", "minValue": 3000, "maxValue": 5000, "unitText": "MONTH"},
        },
    }
    html = (
        "<html><head><script type=\"application/ld+json\">"
        f"{json.dumps(payload)}"
        "</script></head><body></body></html>"
    )

    oferta = extract_jobposting_json_ld(html, "https://example.com/jobs/ai-engineer", "linkedin")

    assert oferta is not None
    assert oferta.titulo == "AI Engineer"
    assert oferta.empresa == "Acme AI"
    assert oferta.modalidad == "remoto"
    assert oferta.ubicacion == "Chile"
    assert "Python" in oferta.requisitos
    assert oferta.salario.startswith("3000-5000 USD")

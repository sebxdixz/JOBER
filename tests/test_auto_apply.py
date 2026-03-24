from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from jober.agents.auto_apply import (
    _detect_ats,
    _direct_apply_url,
    _markdown_to_text,
    _wait_for_form_context,
    auto_apply_to_job,
)
from jober.core.models import OfertaTrabajo, PerfilMaestro


def _perfil_base() -> PerfilMaestro:
    return PerfilMaestro(
        nombre="Sebastian Diaz",
        email="sdiazdelafuente9@gmail.com",
        telefono="+56935900264",
        ubicacion_actual="Chile",
        links={
            "LinkedIn": "https://linkedin.com/in/sdiaz",
            "GitHub": "https://github.com/sdiaz",
        },
    )


def _local_tmp_dir() -> Path:
    tmp_dir = Path(__file__).resolve().parent / "_tmp_auto_apply"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def test_detect_ats():
    assert _detect_ats("https://jobs.lever.co/acme/123") == "lever"
    assert _detect_ats("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert _detect_ats("https://job-boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert _detect_ats("https://www.getonbrd.com/empleos/data/ai-engineer") == "getonbrd"
    assert _detect_ats("https://example.com/jobs/123") == "unsupported"


def test_direct_apply_url():
    assert _direct_apply_url(
        "https://jobs.lever.co/acme/abc123",
        "lever",
    ).endswith("/apply")
    assert _direct_apply_url(
        "https://boards.greenhouse.io/acme/jobs/1234567",
        "greenhouse",
    ).endswith("/applications/new")
    assert _direct_apply_url(
        "https://www.getonbrd.com/empleos/data/ai-engineer",
        "getonbrd",
    ) == "https://www.getonbrd.com/empleos/data/ai-engineer"


def test_markdown_to_text_strips_basic_formatting():
    text = _markdown_to_text(
        "# Hola\n\n**Texto** con [link](https://example.com)\n\n- Item"
    )

    assert "Hola" in text
    assert "Texto con link" in text
    assert "Item" in text


class _FakeContext:
    def __init__(self, url: str = "", selectors: set[str] | None = None):
        self.url = url
        self._selectors = selectors or set()

    async def wait_for_selector(self, selector: str, state: str = "attached", timeout: int = 0):
        if selector in self._selectors:
            return object()
        raise PlaywrightTimeoutError("Timeout")

    def locator(self, selector: str):  # pragma: no cover - no se usa en este test
        raise NotImplementedError(selector)


class _FakePage(_FakeContext):
    def __init__(
        self,
        url: str = "",
        selectors: set[str] | None = None,
        frames: list[object] | None = None,
    ):
        super().__init__(url=url, selectors=selectors)
        self.main_frame = object()
        self.frames = [self.main_frame, *(frames or [])]


@pytest.mark.asyncio
async def test_wait_for_form_context_detects_iframe_when_main_page_is_empty():
    child_frame = _FakeContext(
        url="https://boards.greenhouse.io/embed/job_app",
        selectors={"input[name='first_name']"},
    )
    page = _FakePage(
        url="https://boards.greenhouse.io/acme/jobs/123",
        selectors=set(),
        frames=[child_frame],
    )

    context = await _wait_for_form_context(
        page,
        ("input[name='first_name']",),
        frame_hints=("greenhouse", "grnhse"),
    )

    assert context is child_frame


@pytest.mark.asyncio
async def test_auto_apply_returns_manual_required_for_unsupported_ats():
    cv_pdf = _local_tmp_dir() / "unsupported_cv.pdf"
    cv_pdf.write_text("fake pdf")
    oferta = OfertaTrabajo(
        url="https://example.com/jobs/123",
        titulo="AI Engineer",
        empresa="Acme",
        plataforma="web",
    )

    result = await auto_apply_to_job(oferta, _perfil_base(), cv_pdf)

    assert result.enviado is False
    assert result.mensaje == "ATS no soportado. Postulación manual requerida."


@pytest.mark.asyncio
async def test_auto_apply_rejects_missing_cv():
    oferta = OfertaTrabajo(
        url="https://jobs.lever.co/acme/123",
        titulo="AI Engineer",
        empresa="Acme",
        plataforma="lever",
    )

    result = await auto_apply_to_job(
        oferta,
        _perfil_base(),
        _local_tmp_dir() / "missing.pdf",
    )

    assert result.enviado is False
    assert result.mensaje == "No existe el PDF del CV adaptado para subir."

from __future__ import annotations

from jober.agents.auto_apply import (
    _ats_application_url,
    _detect_ats_provider,
    _file_kind,
    _match_select_option,
    _parse_vision_click_response,
    _should_enable_choice,
    _summarize_a11y_tree,
)
from jober.core.models import OfertaTrabajo, PerfilMaestro


def _perfil_base() -> PerfilMaestro:
    perfil = PerfilMaestro(
        nombre="Sebastian Diaz",
        email="sdiazdelafuente9@gmail.com",
        telefono="+56935900264",
        ubicacion_actual="Chile",
    )
    perfil.preferencias.anos_experiencia = 2
    perfil.preferencias.paises_permitidos = ["Chile", "Remote"]
    return perfil


def test_match_select_option_by_experience():
    meta = {
        "name": "years_of_experience",
        "labels": "Years of experience",
        "options": [
            {"label": "1 year", "value": "1"},
            {"label": "2 years", "value": "2"},
            {"label": "5 years", "value": "5"},
        ],
    }
    oferta = OfertaTrabajo(titulo="AI Engineer", empresa="Acme")

    option = _match_select_option(meta, _perfil_base(), oferta, "")

    assert option is not None
    assert option["value"] == "2"


def test_match_select_option_by_location():
    meta = {
        "name": "country",
        "labels": "Country",
        "options": [
            {"label": "Argentina", "value": "AR"},
            {"label": "Chile", "value": "CL"},
        ],
    }
    oferta = OfertaTrabajo(titulo="ML Engineer", empresa="Acme")

    option = _match_select_option(meta, _perfil_base(), oferta, "")

    assert option is not None
    assert option["value"] == "CL"


def test_should_enable_choice_for_privacy_consent():
    assert _should_enable_choice({
        "labels": "I agree to the privacy policy and data processing terms",
    }) is True
    assert _should_enable_choice({
        "labels": "Do you require visa sponsorship?",
    }) is False


def test_file_kind_detects_resume_and_cover_letter():
    assert _file_kind({
        "labels": "Resume / CV",
        "accept": ".pdf,.docx",
    }) == "cv"
    assert _file_kind({
        "labels": "Cover Letter",
        "accept": ".pdf",
    }) == "cover_letter"


def test_detect_ats_provider():
    assert _detect_ats_provider("https://jobs.lever.co/acme/123") == "lever"
    assert _detect_ats_provider("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert _detect_ats_provider("https://acme.workable.com/jobs/123") == "workable"
    assert _detect_ats_provider("https://jobs.ashbyhq.com/acme/123") == "ashby"
    assert _detect_ats_provider("https://www.linkedin.com/jobs/view/123") == "linkedin"
    assert _detect_ats_provider("https://example.com/apply/123") == "generic_ats"


def test_ats_application_url():
    assert _ats_application_url("https://jobs.lever.co/acme/abc123", "lever").endswith("/apply")
    assert _ats_application_url(
        "https://boards.greenhouse.io/acme/jobs/1234567",
        "greenhouse",
    ).endswith("/applications/new")
    assert _ats_application_url("https://example.com/job/1", "generic") == "https://example.com/job/1"


def test_summarize_a11y_tree():
    snapshot = {
        "role": "WebArea",
        "name": "Application",
        "children": [
            {"role": "heading", "name": "Apply for this job"},
            {
                "role": "form",
                "name": "Application form",
                "children": [
                    {"role": "textbox", "name": "Email", "required": True},
                    {"role": "button", "name": "Submit application"},
                ],
            },
        ],
    }

    summary = _summarize_a11y_tree(snapshot)

    assert "textbox: Email [required]" in summary
    assert "button: Submit application" in summary


def test_parse_vision_click_response():
    parsed = _parse_vision_click_response(
        """```json
        {"click": true, "x": 120, "y": 340, "target": "Submit application", "reason": "Visible primary CTA"}
        ```"""
    )

    assert parsed is not None
    assert parsed["click"] is True
    assert parsed["x"] == 120
    assert parsed["y"] == 340
    assert parsed["target"] == "Submit application"

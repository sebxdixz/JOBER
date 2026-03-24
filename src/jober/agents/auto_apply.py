"""Agente de auto-aplicacion via navegador.

Implementa una capa conservadora de envio real:
- intenta abrir la oferta y encontrar el flujo de postulacion
- completa campos comunes usando el perfil maestro
- sube CV/cover letter cuando el formulario lo soporta
- solo envia si no quedan campos requeridos desconocidos
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from jober.core.config import get_vision_llm
from jober.core.models import OfertaTrabajo, PerfilMaestro, ResultadoAplicacion
from jober.utils.llm_helpers import strip_markdown_fences


SUCCESS_PATTERNS = [
    "application submitted",
    "application sent",
    "applied successfully",
    "thanks for applying",
    "thank you for applying",
    "postulacion enviada",
    "postulación enviada",
    "solicitud enviada",
    "gracias por postular",
]

APPLY_BUTTON_TEXTS = [
    "apply",
    "apply now",
    "easy apply",
    "submit application",
    "postular",
    "postularme",
    "aplicar",
    "solicitar",
]

SUBMIT_BUTTON_TEXTS = [
    "submit",
    "send",
    "apply",
    "continue",
    "finish",
    "enviar",
    "postular",
    "aplicar",
    "continuar",
    "finalizar",
]

PROGRESSION_BUTTON_TEXTS = [
    "continue",
    "next",
    "review",
    "save and continue",
    "continue application",
    "continuar",
    "siguiente",
    "revisar",
]

ATS_OPEN_SELECTORS = {
    "lever": [
        "a[href$='/apply']",
        "a[href*='/apply?']",
        "a:has-text('Apply for this job')",
        "button:has-text('Apply for this job')",
    ],
    "greenhouse": [
        "a[href*='/applications/new']",
        "a[href*='greenhouse.io'][href*='applications']",
        "#application_button",
        "a:has-text('Apply')",
        "button:has-text('Apply')",
    ],
    "workable": [
        "a[href*='/apply']",
        "button[data-ui='apply-button']",
        "button:has-text('Apply')",
    ],
    "ashby": [
        "a[href*='/application']",
        "button:has-text('Apply')",
    ],
}

ATS_PROGRESS_SELECTORS = {
    "lever": [
        "button:has-text('Next')",
        "button:has-text('Review')",
        "button:has-text('Continue')",
    ],
    "greenhouse": [
        "button:has-text('Next')",
        "button:has-text('Review Application')",
    ],
}

ATS_SUBMIT_SELECTORS = {
    "lever": [
        "button[type='submit']",
        "button:has-text('Submit application')",
    ],
    "greenhouse": [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit Application')",
    ],
}

VISION_CLICK_PROMPT = """Eres un agente de navegacion visual.
Recibes un screenshot de una pagina de postulacion laboral y una instruccion.
Debes responder SOLO JSON valido con este formato:
{
  "click": true|false,
  "x": 123,
  "y": 456,
  "target": "descripcion corta",
  "reason": "explicacion breve"
}

Reglas:
- Usa coordenadas absolutas dentro de la imagen.
- Si no hay un objetivo confiable, responde {"click": false, ...}.
- Prioriza botones Apply/Next/Continue/Submit y checkboxes de consentimiento.
- No inventes elementos que no se vean claramente.
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _detect_ats_provider(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    path = urlparse(url or "").path.lower()

    if "lever.co" in host:
        return "lever"
    if "greenhouse.io" in host:
        return "greenhouse"
    if "workable.com" in host:
        return "workable"
    if "ashbyhq.com" in host:
        return "ashby"
    if "linkedin.com" in host:
        return "linkedin"
    if "getonbrd.com" in host:
        return "getonbrd"
    if "/apply" in path or "/application" in path:
        return "generic_ats"
    return "generic"


def _ats_application_url(url: str, ats_provider: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url

    clean = url.rstrip("/")
    if ats_provider == "lever" and not clean.endswith("/apply"):
        return f"{clean}/apply"
    if ats_provider == "greenhouse" and "/applications/new" not in clean:
        return f"{clean}/applications/new"
    if ats_provider == "workable" and not clean.endswith("/apply"):
        return f"{clean}/apply"
    if ats_provider == "ashby" and "/application" not in clean:
        return f"{clean}/application"
    return url


def _markdown_to_text(markdown: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", markdown)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>-]", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _flatten_a11y_tree(node: dict | None, depth: int = 0, limit: int = 80) -> list[str]:
    if not isinstance(node, dict) or limit <= 0:
        return []

    role = str(node.get("role", "")).strip()
    name = str(node.get("name", "")).strip()
    if not role and not name:
        lines: list[str] = []
    else:
        state_bits: list[str] = []
        if node.get("focused"):
            state_bits.append("focused")
        if node.get("disabled"):
            state_bits.append("disabled")
        if node.get("checked") is True:
            state_bits.append("checked")
        if node.get("required"):
            state_bits.append("required")
        suffix = f" [{' '.join(state_bits)}]" if state_bits else ""
        lines = [f"{'  ' * depth}{role or 'node'}: {name or '-'}{suffix}"]

    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            if len(lines) >= limit:
                break
            lines.extend(_flatten_a11y_tree(child, depth + 1, limit - len(lines)))

    return lines[:limit]


def _summarize_a11y_tree(snapshot: dict | None, limit: int = 40) -> str:
    lines = _flatten_a11y_tree(snapshot, limit=limit)
    return "\n".join(lines[:limit]).strip()


def _profile_links(perfil: PerfilMaestro) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in perfil.links.items():
        normalized[_normalize(key)] = value
    return normalized


async def _fill_first_visible(page: Page, selectors: list[str], value: str) -> bool:
    if not value.strip():
        return False
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            await locator.fill(value)
            return True
        except Exception:
            continue
    return False


async def _upload_first_visible(page: Page, selectors: list[str], file_path: Path) -> bool:
    if not file_path.exists():
        return False
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            await locator.set_input_files(str(file_path))
            return True
        except Exception:
            continue
    return False


async def _field_metadata(locator) -> dict[str, object]:
    return await locator.evaluate(
        """el => {
            const labels = [];
            if (el.labels) {
                for (const label of el.labels) {
                    labels.push((label.innerText || label.textContent || "").trim());
                }
            }
            if (!labels.length && el.id) {
                const explicit = document.querySelector(`label[for="${el.id}"]`);
                if (explicit) labels.push((explicit.innerText || explicit.textContent || "").trim());
            }
            return {
                tag: el.tagName.toLowerCase(),
                type: (el.getAttribute("type") || "").toLowerCase(),
                name: el.getAttribute("name") || "",
                id: el.getAttribute("id") || "",
                placeholder: el.getAttribute("placeholder") || "",
                aria_label: el.getAttribute("aria-label") || "",
                accept: el.getAttribute("accept") || "",
                required: !!el.required || el.getAttribute("aria-required") === "true",
                disabled: !!el.disabled,
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                labels: labels.join(" | "),
                value: el.value || "",
                checked: !!el.checked,
                options: el.tagName.toLowerCase() === "select"
                    ? Array.from(el.options || []).map(opt => ({
                        label: (opt.label || opt.textContent || "").trim(),
                        value: opt.value || "",
                        selected: !!opt.selected,
                    }))
                    : [],
            };
        }"""
    )


def _match_value(meta: dict[str, object], perfil: PerfilMaestro, oferta: OfertaTrabajo, cover_letter: str) -> str | None:
    blob = _normalize(
        " ".join(
            str(meta.get(key, ""))
            for key in ("name", "id", "placeholder", "aria_label", "labels")
        )
    )
    links = _profile_links(perfil)

    if any(key in blob for key in ["email", "e-mail", "correo"]):
        return perfil.email
    if any(key in blob for key in ["phone", "mobile", "telefono", "teléfono", "whatsapp", "cell"]):
        return perfil.telefono
    if "linkedin" in blob:
        return links.get("linkedin", "")
    if "github" in blob:
        return links.get("github", "")
    if any(key in blob for key in ["portfolio", "website", "personal site", "sitio web", "web"]):
        return (
            links.get("portfolio", "")
            or links.get("website", "")
            or links.get("sitio web", "")
            or links.get("web", "")
        )
    if any(key in blob for key in ["full name", "nombre completo"]):
        return perfil.nombre
    if any(key in blob for key in ["first name", "nombre"]) and "company" not in blob:
        return perfil.nombre.split(" ")[0] if perfil.nombre else ""
    if any(key in blob for key in ["last name", "apellido"]):
        return " ".join(perfil.nombre.split(" ")[1:]) if len(perfil.nombre.split(" ")) > 1 else ""
    if any(key in blob for key in ["location", "city", "ciudad", "ubicacion", "ubicación", "address", "direccion", "dirección"]):
        return perfil.ubicacion_actual
    if any(key in blob for key in ["title", "headline", "current role", "cargo actual"]):
        return perfil.titulo_profesional
    if any(key in blob for key in ["summary", "about", "bio", "profile", "sobre ti", "acerca"]):
        return perfil.resumen
    if any(
        key in blob
        for key in [
            "cover letter",
            "message",
            "mensaje",
            "why do you want",
            "why are you interested",
            "additional information",
            "tell us about yourself",
            "carta",
            "motivation",
        ]
    ):
        return cover_letter
    if "company" in blob and not any(key in blob for key in ["linkedin", "github"]):
        return oferta.empresa
    return None


def _file_kind(meta: dict[str, object]) -> str | None:
    blob = _normalize(
        " ".join(
            str(meta.get(key, ""))
            for key in ("name", "id", "placeholder", "aria_label", "labels", "accept")
        )
    )
    if any(key in blob for key in ["cover", "carta"]):
        return "cover_letter"
    if any(key in blob for key in ["resume", "cv", "curriculum", "curriculo", "currículum"]):
        return "cv"
    accept = str(meta.get("accept", "")).lower()
    if "pdf" in accept or "doc" in accept:
        return "cv"
    return None


def _choice_blob(meta: dict[str, object]) -> str:
    return _normalize(
        " ".join(
            str(meta.get(key, ""))
            for key in ("name", "id", "placeholder", "aria_label", "labels")
        )
    )


def _match_select_option(meta: dict[str, object], perfil: PerfilMaestro, oferta: OfertaTrabajo, cover_letter_text: str) -> dict[str, str] | None:
    options = meta.get("options", [])
    if not isinstance(options, list) or not options:
        return None

    def _pick_by_targets(targets: list[str]) -> dict[str, str] | None:
        normalized_targets = [_normalize(target) for target in targets if target and str(target).strip()]
        if not normalized_targets:
            return None
        for option in options:
            if not isinstance(option, dict):
                continue
            label = _normalize(str(option.get("label", "")))
            value = _normalize(str(option.get("value", "")))
            for target in normalized_targets:
                if target and (target in label or label in target or target in value):
                    return {
                        "label": str(option.get("label", "")),
                        "value": str(option.get("value", "")),
                    }
        return None

    direct_value = _match_value(meta, perfil, oferta, cover_letter_text)
    direct_match = _pick_by_targets([direct_value or ""])
    if direct_match:
        return direct_match

    blob = _choice_blob(meta)
    if any(token in blob for token in ["experience", "years", "anos", "años"]):
        experience = str(perfil.preferencias.anos_experiencia or "")
        experience_match = _pick_by_targets([experience, f"{experience}+", f"{experience} years"])
        if experience_match:
            return experience_match

    if any(token in blob for token in ["country", "pais", "país", "location", "city", "ciudad"]):
        location_targets = [
            perfil.ubicacion_actual,
            *perfil.preferencias.ubicaciones,
            *perfil.preferencias.paises_permitidos,
        ]
        location_match = _pick_by_targets(location_targets)
        if location_match:
            return location_match

    return None


def _should_enable_choice(meta: dict[str, object]) -> bool:
    blob = _choice_blob(meta)
    safe_markers = [
        "privacy",
        "terms",
        "consent",
        "gdpr",
        "data processing",
        "i agree",
        "accept",
        "acepto",
        "autorizo",
        "tratamiento de datos",
        "politica de privacidad",
        "política de privacidad",
    ]
    return any(marker in blob for marker in safe_markers)


async def _fill_greenhouse_specific(
    page: Page,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
) -> dict[str, str]:
    details: dict[str, str] = {}
    full_name = perfil.nombre.strip()
    first_name = full_name.split(" ")[0] if full_name else ""
    last_name = " ".join(full_name.split(" ")[1:]) if len(full_name.split(" ")) > 1 else ""
    links = _profile_links(perfil)

    mappings = [
        ("gh_first_name", ["#first_name", "input[name='first_name']", "input[id*='first_name']"], first_name),
        ("gh_last_name", ["#last_name", "input[name='last_name']", "input[id*='last_name']"], last_name),
        ("gh_name", ["#name", "input[name='name']"], full_name),
        ("gh_email", ["#email", "input[name='email']", "input[type='email']"], perfil.email),
        ("gh_phone", ["#phone", "input[name='phone']", "input[type='tel']"], perfil.telefono),
        ("gh_location", ["#auto_complete_input", "input[name='location']", "input[id*='location']"], perfil.ubicacion_actual),
        ("gh_linkedin", ["input[name*='linkedin']", "input[id*='linkedin']"], links.get("linkedin", "")),
        ("gh_github", ["input[name*='github']", "input[id*='github']"], links.get("github", "")),
        ("gh_website", ["input[name*='website']", "input[name*='portfolio']"], links.get("portfolio", "") or links.get("website", "")),
        ("gh_cover", ["textarea[name='cover_letter']", "#cover_letter", "textarea[id*='cover_letter']"], cover_letter_text),
    ]

    for key, selectors, value in mappings:
        if await _fill_first_visible(page, selectors, value or ""):
            details[key] = "filled"

    if await _upload_first_visible(
        page,
        [
            "input[type='file'][name='resume']",
            "input[type='file'][id*='resume']",
            "input[type='file'][name*='resume']",
        ],
        cv_pdf,
    ):
        details["gh_resume"] = str(cv_pdf)

    if cover_letter_pdf is not None and await _upload_first_visible(
        page,
        [
            "input[type='file'][name='cover_letter']",
            "input[type='file'][id*='cover_letter']",
            "input[type='file'][name*='cover_letter']",
        ],
        cover_letter_pdf,
    ):
        details["gh_cover_file"] = str(cover_letter_pdf)

    return details


async def _fill_lever_specific(
    page: Page,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
) -> dict[str, str]:
    details: dict[str, str] = {}
    links = _profile_links(perfil)

    mappings = [
        ("lever_name", ["input[name='name']", "input[id='name']"], perfil.nombre),
        ("lever_email", ["input[name='email']", "input[type='email']"], perfil.email),
        ("lever_phone", ["input[name='phone']", "input[type='tel']"], perfil.telefono),
        ("lever_location", ["input[name='location']", "input[id*='location']"], perfil.ubicacion_actual),
        ("lever_company", ["input[name='company']", "input[id*='company']"], ""),
        ("lever_linkedin", ["input[name='urls[LinkedIn]']", "input[name*='linkedin']"], links.get("linkedin", "")),
        ("lever_github", ["input[name='urls[Github]']", "input[name*='github']"], links.get("github", "")),
        ("lever_portfolio", ["input[name='urls[Portfolio]']", "input[name*='portfolio']", "input[name*='website']"], links.get("portfolio", "") or links.get("website", "")),
        ("lever_comments", ["textarea[name='comments']", "textarea[id*='comments']"], cover_letter_text),
    ]

    for key, selectors, value in mappings:
        if await _fill_first_visible(page, selectors, value or ""):
            details[key] = "filled"

    if await _upload_first_visible(
        page,
        [
            "input[type='file'][name='resume']",
            "input[type='file'][name='resume[]']",
            "input[type='file'][name*='resume']",
        ],
        cv_pdf,
    ):
        details["lever_resume"] = str(cv_pdf)

    if cover_letter_pdf is not None and await _upload_first_visible(
        page,
        [
            "input[type='file'][name='coverLetter']",
            "input[type='file'][name*='cover']",
        ],
        cover_letter_pdf,
    ):
        details["lever_cover_file"] = str(cover_letter_pdf)

    return details


async def _fill_ats_specific(
    page: Page,
    ats_provider: str,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
) -> dict[str, str]:
    if ats_provider == "greenhouse":
        return await _fill_greenhouse_specific(page, perfil, cv_pdf, cover_letter_pdf, cover_letter_text)
    if ats_provider == "lever":
        return await _fill_lever_specific(page, perfil, cv_pdf, cover_letter_pdf, cover_letter_text)
    return {}


async def _fill_form(
    page: Page,
    perfil: PerfilMaestro,
    oferta: OfertaTrabajo,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    ats_provider: str = "generic",
) -> dict[str, str]:
    details: dict[str, str] = await _fill_ats_specific(
        page,
        ats_provider,
        perfil,
        cv_pdf,
        cover_letter_pdf,
        cover_letter_text,
    )
    fields = page.locator("input, textarea, select")
    count = await fields.count()
    uploaded_cv = False
    uploaded_cover = False
    filled_count = 0

    for idx in range(count):
        locator = fields.nth(idx)
        try:
            meta = await _field_metadata(locator)
        except Exception:
            continue

        if bool(meta.get("disabled")):
            continue

        tag = str(meta.get("tag", ""))
        input_type = str(meta.get("type", ""))

        if input_type == "file":
            kind = _file_kind(meta)
            if kind == "cv" and cv_pdf.exists():
                await locator.set_input_files(str(cv_pdf))
                uploaded_cv = True
                details[f"file_{idx}"] = "cv"
                continue
            if kind == "cover_letter" and cover_letter_pdf is not None and cover_letter_pdf.exists():
                await locator.set_input_files(str(cover_letter_pdf))
                uploaded_cover = True
                details[f"file_{idx}"] = "cover_letter"
                continue
            continue

        if not bool(meta.get("visible")):
            continue

        if input_type in {"hidden", "submit", "button"}:
            continue

        if input_type in {"checkbox", "radio"}:
            if _should_enable_choice(meta) and not bool(meta.get("checked")):
                try:
                    await locator.check(force=True)
                    details[f"choice_{idx}"] = str(meta.get("name") or meta.get("id") or meta.get("labels") or f"choice_{idx}")
                    filled_count += 1
                except Exception:
                    continue
            continue

        if tag == "select":
            option = _match_select_option(meta, perfil, oferta, cover_letter_text)
            if option is None:
                continue
            try:
                value = option.get("value", "")
                label = option.get("label", "")
                if value:
                    await locator.select_option(value=value)
                elif label:
                    await locator.select_option(label=label)
                else:
                    continue
                details[f"field_{idx}"] = label or value or str(meta.get("labels") or meta.get("name") or meta.get("id") or f"field_{idx}")
                filled_count += 1
            except Exception:
                continue
            continue

        value = _match_value(meta, perfil, oferta, cover_letter_text)
        if not value:
            continue

        try:
            await locator.fill(value)
            details[f"field_{idx}"] = str(meta.get("name") or meta.get("id") or meta.get("labels") or f"field_{idx}")
            filled_count += 1
        except Exception:
            continue

    if uploaded_cv:
        details["uploaded_cv"] = str(cv_pdf)
    if uploaded_cover and cover_letter_pdf is not None:
        details["uploaded_cover_letter"] = str(cover_letter_pdf)
    details["filled_count"] = str(filled_count)

    return details


async def _remaining_required_fields(page: Page) -> list[str]:
    fields = page.locator("input, textarea, select")
    count = await fields.count()
    missing: list[str] = []
    seen_radio_groups: set[str] = set()

    for idx in range(count):
        locator = fields.nth(idx)
        try:
            meta = await _field_metadata(locator)
        except Exception:
            continue

        input_type = str(meta.get("type", ""))
        is_file = input_type == "file"
        if bool(meta.get("disabled")) or not bool(meta.get("required")):
            continue
        if not bool(meta.get("visible")) and not is_file:
            continue

        if input_type in {"hidden", "submit", "button"}:
            continue

        if input_type == "file":
            js_empty = await locator.evaluate("el => !el.files || el.files.length === 0")
        elif input_type == "checkbox":
            js_empty = not bool(meta.get("checked"))
        elif input_type == "radio":
            group_name = str(meta.get("name", "")).strip()
            if group_name and group_name in seen_radio_groups:
                continue
            if group_name:
                seen_radio_groups.add(group_name)
                js_empty = await locator.evaluate(
                    """el => {
                        const name = el.getAttribute('name');
                        if (!name) return !el.checked;
                        const group = document.querySelectorAll(`input[type="radio"][name="${name}"]`);
                        return !Array.from(group).some(item => item.checked);
                    }"""
                )
            else:
                js_empty = not bool(meta.get("checked"))
        elif str(meta.get("tag", "")) == "select":
            js_empty = await locator.evaluate("el => !el.value")
        else:
            js_empty = not str(meta.get("value", "")).strip()

        if js_empty:
            missing.append(str(meta.get("labels") or meta.get("name") or meta.get("id") or f"field_{idx}"))

    return missing


async def _find_clickable(page: Page, texts: list[str]):
    for text in texts:
        candidates = [
            page.get_by_role("button", name=re.compile(text, re.I)),
            page.get_by_role("link", name=re.compile(text, re.I)),
            page.locator(f"button:has-text('{text}')"),
            page.locator(f"a:has-text('{text}')"),
        ]
        for locator in candidates:
            try:
                if await locator.first.is_visible():
                    return locator.first
            except Exception:
                continue
    return None


async def _find_by_selectors(page: Page, selectors: list[str]):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible():
                return locator
        except Exception:
            continue
    return None


async def _page_has_form_fields(page: Page) -> bool:
    try:
        count = await page.locator("input, textarea, select").count()
        return count > 2
    except Exception:
        return False


async def _capture_a11y_summary(page: Page, limit: int = 40) -> str:
    try:
        snapshot = await page.accessibility.snapshot(interesting_only=True)
    except Exception:
        return ""
    return _summarize_a11y_tree(snapshot, limit=limit)


def _vision_enabled() -> bool:
    return os.getenv("JOBER_VISION_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_vision_click_response(text: str) -> dict[str, object] | None:
    if not text:
        return None
    try:
        payload = json.loads(strip_markdown_fences(text))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    click = bool(payload.get("click"))
    try:
        x = int(round(float(payload.get("x", 0))))
        y = int(round(float(payload.get("y", 0))))
    except Exception:
        x, y = 0, 0

    return {
        "click": click,
        "x": x,
        "y": y,
        "target": str(payload.get("target", "")).strip(),
        "reason": str(payload.get("reason", "")).strip(),
    }


async def _vision_click(
    page: Page,
    instruction: str,
    *,
    a11y_summary: str = "",
) -> dict[str, object] | None:
    if not _vision_enabled():
        return None

    screenshot = await page.screenshot(type="png")
    image_b64 = base64.b64encode(screenshot).decode("utf-8")
    llm = get_vision_llm(temperature=0.0)

    prompt = (
        f"Instruccion: {instruction}\n"
        f"URL actual: {page.url}\n"
        f"Resumen A11y:\n{a11y_summary[:3000] if a11y_summary else '(sin resumen)'}"
    )
    response = await llm.ainvoke([
        SystemMessage(content=VISION_CLICK_PROMPT),
        HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]),
    ])

    raw_content = response.content
    if isinstance(raw_content, list):
        text_parts = []
        for item in raw_content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        raw_text = "\n".join(text_parts)
    else:
        raw_text = str(raw_content)

    parsed = _parse_vision_click_response(raw_text)
    if not parsed or not parsed.get("click"):
        return parsed

    await page.mouse.click(int(parsed["x"]), int(parsed["y"]))
    await page.wait_for_timeout(1200)
    return parsed


async def _locator_text(locator) -> str:
    try:
        text = await locator.inner_text()
        if text.strip():
            return text.strip()
    except Exception:
        pass
    try:
        aria = await locator.get_attribute("aria-label")
        if aria and aria.strip():
            return aria.strip()
    except Exception:
        pass
    return ""


async def _open_application_flow(page: Page, ats_provider: str) -> tuple[bool, str]:
    if await _page_has_form_fields(page):
        return True, "form_already_visible"

    direct_url = _ats_application_url(page.url, ats_provider)
    if direct_url and direct_url != page.url:
        try:
            await page.goto(direct_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
            if await _page_has_form_fields(page):
                return True, "direct_ats_url"
        except Exception:
            pass

    button = None
    selectors = ATS_OPEN_SELECTORS.get(ats_provider, [])
    if selectors:
        button = await _find_by_selectors(page, selectors)
    if button is None:
        button = await _find_clickable(page, APPLY_BUTTON_TEXTS)
    if button is None:
        vision = await _vision_click(
            page,
            "Haz click en el boton principal para comenzar la postulacion. Prioriza Apply, Postular o Easy Apply.",
            a11y_summary=await _capture_a11y_summary(page),
        )
        if vision and vision.get("click"):
            return True, f"vision:{vision.get('target') or 'apply'}"
        return False, ""

    context = page.context
    before_pages = len(context.pages)
    try:
        label = await _locator_text(button)
        href = await button.get_attribute("href")
        if href and any(marker in href.lower() for marker in ["/apply", "/application", "applications/new"]):
            await page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=30000)
        else:
            await button.click()
    except Exception:
        return False, ""

    await page.wait_for_timeout(2500)
    if len(context.pages) > before_pages:
        new_page = context.pages[-1]
        await new_page.wait_for_load_state("domcontentloaded")
    return True, label


async def _active_page(page: Page) -> Page:
    return page.context.pages[-1]


async def _click_action_button(page: Page, ats_provider: str) -> tuple[bool, str, str]:
    groups: list[tuple[str, object]] = []
    if ats_provider in ATS_PROGRESS_SELECTORS:
        groups.append(("progress", ATS_PROGRESS_SELECTORS[ats_provider]))
    groups.append(("progress", PROGRESSION_BUTTON_TEXTS))
    if ats_provider in ATS_SUBMIT_SELECTORS:
        groups.append(("submit", ATS_SUBMIT_SELECTORS[ats_provider]))
    groups.append(("submit", SUBMIT_BUTTON_TEXTS))

    for group_name, matcher in groups:
        if isinstance(matcher, list) and matcher and str(matcher[0]).startswith(("button", "a", "input", "#", ".")):
            button = await _find_by_selectors(page, matcher)
        else:
            button = await _find_clickable(page, matcher)
        if button is None:
            continue
        try:
            label = await _locator_text(button)
            await button.click()
            return True, group_name, label
        except Exception:
            continue
    vision = await _vision_click(
        page,
        "Haz click en el boton principal para avanzar o enviar esta postulacion. Prioriza Submit/Application/Next/Continue/Review.",
        a11y_summary=await _capture_a11y_summary(page),
    )
    if vision and vision.get("click"):
        target = _normalize(str(vision.get("target", "")))
        if any(token in target for token in ["submit", "send", "apply", "enviar", "postular"]):
            return True, "submit", str(vision.get("target", "vision_submit"))
        return True, "progress", str(vision.get("target", "vision_progress"))
    return False, "", ""


async def _looks_successful(page: Page) -> bool:
    body_text = _normalize(await page.locator("body").inner_text())
    return any(pattern in body_text for pattern in SUCCESS_PATTERNS)


async def auto_apply_to_job(
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None = None,
    cover_letter_md: str = "",
) -> ResultadoAplicacion:
    """Intenta enviar una postulacion real con heuristicas conservadoras."""
    result = ResultadoAplicacion(
        enviado=False,
        metodo="browser_heuristic",
        plataforma=oferta.plataforma,
        url_final=oferta.url,
    )

    if not oferta.url:
        result.mensaje = "La oferta no tiene URL."
        return result
    if not cv_pdf.exists():
        result.mensaje = "No existe el PDF del CV adaptado para subir."
        return result
    if not perfil.nombre or not perfil.email:
        result.mensaje = "Faltan datos minimos del perfil para auto-aplicar (nombre y email)."
        return result

    cover_letter_text = _markdown_to_text(cover_letter_md)
    ats_provider = _detect_ats_provider(oferta.url)
    result.detalles["ats_provider"] = ats_provider

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()
            await page.goto(oferta.url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            initial_a11y = await _capture_a11y_summary(page)
            if initial_a11y:
                result.detalles["a11y_initial"] = initial_a11y

            opened, open_label = await _open_application_flow(page, ats_provider)
            result.detalles["opened_application_flow"] = str(opened).lower()
            if open_label:
                result.detalles["apply_button_label"] = open_label
            target_page = await _active_page(page)
            await target_page.wait_for_timeout(1500)
            target_a11y = await _capture_a11y_summary(target_page)
            if target_a11y:
                result.detalles["a11y_form"] = target_a11y
            submitted = False
            last_action = ""

            for step in range(5):
                result.detalles[f"step_{step}_url_before"] = target_page.url

                fill_details = await _fill_form(
                    target_page,
                    perfil,
                    oferta,
                    cv_pdf=cv_pdf,
                    cover_letter_pdf=cover_letter_pdf,
                    cover_letter_text=cover_letter_text,
                    ats_provider=ats_provider,
                )
                for key, value in fill_details.items():
                    result.detalles[f"step_{step}_{key}"] = value

                missing = await _remaining_required_fields(target_page)
                if missing:
                    result.mensaje = "Formulario con campos requeridos no soportados."
                    result.detalles["missing_required_fields"] = ", ".join(missing[:10])
                    await browser.close()
                    return result

                clicked, action_kind, action_label = await _click_action_button(target_page, ats_provider)
                if not clicked:
                    result.mensaje = "No se encontro un boton de envio compatible."
                    await browser.close()
                    return result

                last_action = action_label or action_kind
                result.detalles[f"step_{step}_action_kind"] = action_kind
                result.detalles[f"step_{step}_action_label"] = last_action

                try:
                    await target_page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                await target_page.wait_for_timeout(2000)
                target_page = await _active_page(target_page)

                if await _looks_successful(target_page):
                    submitted = True
                    break

                result.detalles[f"step_{step}_url_after"] = target_page.url
                if action_kind == "submit":
                    submitted = True
                    break

            result.url_final = target_page.url
            result.detalles["last_action"] = last_action
            result.detalles["final_url"] = target_page.url
            final_a11y = await _capture_a11y_summary(target_page)
            if final_a11y:
                result.detalles["a11y_final"] = final_a11y
            if await _looks_successful(target_page):
                result.enviado = True
                result.mensaje = "Postulacion enviada."
            elif submitted and target_page.url != oferta.url:
                result.enviado = True
                result.mensaje = "Postulacion enviada."
            elif submitted:
                result.mensaje = "Se intento enviar la postulacion, pero no hubo confirmacion verificable."
            else:
                result.mensaje = "No se pudo completar el flujo de postulacion."

            await browser.close()
    except Exception as exc:
        result.mensaje = f"Fallo el auto-apply: {exc}"

    return result

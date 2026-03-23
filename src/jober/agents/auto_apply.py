"""Agente de auto-aplicacion via navegador.

Implementa una capa conservadora de envio real:
- intenta abrir la oferta y encontrar el flujo de postulacion
- completa campos comunes usando el perfil maestro
- sube CV/cover letter cuando el formulario lo soporta
- solo envia si no quedan campos requeridos desconocidos
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from jober.core.models import OfertaTrabajo, PerfilMaestro, ResultadoAplicacion


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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _markdown_to_text(markdown: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", markdown)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>-]", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _profile_links(perfil: PerfilMaestro) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in perfil.links.items():
        normalized[_normalize(key)] = value
    return normalized


async def _field_metadata(locator) -> dict[str, str | bool]:
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
            };
        }"""
    )


def _match_value(meta: dict[str, str | bool], perfil: PerfilMaestro, oferta: OfertaTrabajo, cover_letter: str) -> str | None:
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


def _file_kind(meta: dict[str, str | bool]) -> str | None:
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


async def _fill_form(page: Page, perfil: PerfilMaestro, oferta: OfertaTrabajo, cv_pdf: Path, cover_letter_pdf: Path | None, cover_letter_text: str) -> dict[str, str]:
    details: dict[str, str] = {}
    fields = page.locator("input, textarea, select")
    count = await fields.count()
    uploaded_cv = False
    uploaded_cover = False

    for idx in range(count):
        locator = fields.nth(idx)
        try:
            meta = await _field_metadata(locator)
        except Exception:
            continue

        if not meta["visible"] or meta["disabled"]:
            continue

        tag = str(meta.get("tag", ""))
        input_type = str(meta.get("type", ""))
        if input_type in {"hidden", "submit", "button", "checkbox", "radio"}:
            continue

        if input_type == "file":
            kind = _file_kind(meta)
            if kind == "cv" and cv_pdf.exists():
                await locator.set_input_files(str(cv_pdf))
                uploaded_cv = True
                continue
            if kind == "cover_letter" and cover_letter_pdf is not None and cover_letter_pdf.exists():
                await locator.set_input_files(str(cover_letter_pdf))
                uploaded_cover = True
                continue
            continue

        value = _match_value(meta, perfil, oferta, cover_letter_text)
        if not value:
            continue

        try:
            if tag == "select":
                await locator.select_option(label=value)
            else:
                await locator.fill(value)
            details[f"field_{idx}"] = str(meta.get("name") or meta.get("id") or meta.get("labels") or f"field_{idx}")
        except Exception:
            continue

    if uploaded_cv:
        details["uploaded_cv"] = str(cv_pdf)
    if uploaded_cover and cover_letter_pdf is not None:
        details["uploaded_cover_letter"] = str(cover_letter_pdf)

    return details


async def _remaining_required_fields(page: Page) -> list[str]:
    fields = page.locator("input, textarea, select")
    count = await fields.count()
    missing: list[str] = []

    for idx in range(count):
        locator = fields.nth(idx)
        try:
            meta = await _field_metadata(locator)
        except Exception:
            continue

        if not meta["visible"] or meta["disabled"] or not meta["required"]:
            continue

        input_type = str(meta.get("type", ""))
        if input_type in {"hidden", "submit", "button"}:
            continue

        if input_type == "file":
            js_empty = await locator.evaluate("el => !el.files || el.files.length === 0")
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


async def _open_application_flow(page: Page) -> None:
    button = await _find_clickable(page, APPLY_BUTTON_TEXTS)
    if button is None:
        return

    context = page.context
    before_pages = len(context.pages)
    try:
        await button.click()
    except Exception:
        return

    await page.wait_for_timeout(2500)
    if len(context.pages) > before_pages:
        new_page = context.pages[-1]
        await new_page.wait_for_load_state("domcontentloaded")


async def _active_page(page: Page) -> Page:
    return page.context.pages[-1]


async def _submit(page: Page) -> bool:
    button = await _find_clickable(page, SUBMIT_BUTTON_TEXTS)
    if button is None:
        return False
    try:
        await button.click()
        return True
    except Exception:
        return False


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

            await _open_application_flow(page)
            target_page = await _active_page(page)
            await target_page.wait_for_timeout(1500)

            fill_details = await _fill_form(
                target_page,
                perfil,
                oferta,
                cv_pdf=cv_pdf,
                cover_letter_pdf=cover_letter_pdf,
                cover_letter_text=cover_letter_text,
            )
            result.detalles.update(fill_details)

            missing = await _remaining_required_fields(target_page)
            if missing:
                result.mensaje = "Formulario con campos requeridos no soportados."
                result.detalles["missing_required_fields"] = ", ".join(missing[:10])
                await browser.close()
                return result

            submitted = await _submit(target_page)
            if not submitted:
                result.mensaje = "No se encontro un boton de envio compatible."
                await browser.close()
                return result

            try:
                await target_page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            await target_page.wait_for_timeout(3000)

            result.url_final = target_page.url
            if await _looks_successful(target_page) or target_page.url != oferta.url:
                result.enviado = True
                result.mensaje = "Postulacion enviada."
            else:
                result.mensaje = "Se hizo click en enviar, pero no hubo confirmacion verificable."

            await browser.close()
    except Exception as exc:
        result.mensaje = f"Fallo el auto-apply: {exc}"

    return result

"""Auto-apply ATS-specific con Playwright.

El parser universal anterior era frágil en producción. Este módulo usa
"modo francotirador": detecta el ATS por URL y ejecuta un flujo rígido para
Greenhouse, Lever o Get on Board.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import urlparse

from playwright.async_api import (
    Error as PlaywrightError,
    Frame,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from jober.core.config import ensure_profile_dirs, get_active_profile_id, get_vision_llm
from jober.core.logging import logger
from jober.core.models import OfertaTrabajo, PerfilMaestro, ResultadoAplicacion

# Browser-use imports for universal agent
try:
    from browser_use import Agent, Browser
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logger.warning("browser-use no está instalado. El agente universal no estará disponible.")


SHORT_TIMEOUT_MS = 60_000
SELECTOR_TIMEOUT_MS = 60_000
NAVIGATION_TIMEOUT_MS = 60_000
MAX_MULTI_STEP_ATTEMPTS = 4
REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

PlaywrightContext = Page | Frame
TraceFn = Callable[[str], None]

GREENHOUSE_FRAME_HINTS = ("greenhouse", "grnhse", "grnh.se")
GREENHOUSE_FORM_SELECTORS = (
    "form#application",
    "form[action*='greenhouse']",
    "form[action*='grnhse']",
    "input[name='first_name']",
    "#first_name",
)
GREENHOUSE_OPEN_SELECTORS = (
    "a[href*='/applications/new']",
    "#application_button",
    "button:has-text('Apply for this job')",
    "a:has-text('Apply for this job')",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
)
GREENHOUSE_SUBMIT_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Submit Application')",
    "button:has-text('Submit')",
)
GREENHOUSE_NEXT_SELECTORS = (
    "button:has-text('Next')",
    "button:has-text('Continue')",
    "button:has-text('Review Application')",
)
GREENHOUSE_CONSENT_SELECTORS = (
    "input[type='checkbox'][name*='privacy']",
    "input[type='checkbox'][name*='consent']",
    "input[type='checkbox'][id*='privacy']",
)

LEVER_FRAME_HINTS = ("lever", "jobs.lever")
LEVER_FORM_SELECTORS = (
    "form[data-qa='application-form']",
    "form#application-form",
    "div.application-page",
    "input[name='name']",
    "input[name='email']",
)
LEVER_OPEN_SELECTORS = (
    "a[href$='/apply']",
    "a[href*='/apply?']",
    "button:has-text('Apply for this job')",
    "a:has-text('Apply for this job')",
)
LEVER_SUBMIT_SELECTORS = (
    "button[type='submit']",
    "button:has-text('Submit application')",
    "button:has-text('Submit Application')",
    "button:has-text('Apply')",
)
LEVER_NEXT_SELECTORS = (
    "button:has-text('Next')",
    "button:has-text('Continue')",
    "button:has-text('Review')",
)
LEVER_CONSENT_SELECTORS = (
    "input[type='checkbox'][name*='consent']",
    "input[type='checkbox'][name*='privacy']",
    "input[type='checkbox'][id*='consent']",
)

GETONBRD_FRAME_HINTS = ("getonbrd",)
GETONBRD_FORM_SELECTORS = (
    "form",
    "input[type='email']",
    "input[name='email']",
    "textarea",
)
GETONBRD_OPEN_SELECTORS = (
    "a[href*='/apply']",
    "button:has-text('Postular')",
    "a:has-text('Postular')",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
)
GETONBRD_SUBMIT_SELECTORS = (
    "button[type='submit']",
    "button:has-text('Enviar')",
    "button:has-text('Postular')",
    "button:has-text('Apply')",
)

FALLBACK_FORM_SELECTORS = (
    "form",
    "input[type='email']",
    "input[name*='email']",
    "input[type='file']",
)
FALLBACK_SUBMIT_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Submit')",
    "button:has-text('Enviar')",
    "button:has-text('Apply')",
    "button:has-text('Postular')",
)
FALLBACK_NEXT_SELECTORS = (
    "button:has-text('Next')",
    "button:has-text('Continue')",
    "button:has-text('Continuar')",
)

LINKEDIN_FORM_SELECTORS = (
    "form",
    "input[name*='first']",
    "input[name*='last']",
    "input[type='email']",
    "input[type='tel']",
)
LINKEDIN_EASY_APPLY_SELECTORS = (
    "button:has-text('Easy Apply')",
    "button:has-text('Solicitud sencilla')",
    "button:has-text('Solicitud fácil')",
    "button:has-text('Solicitar')",  # Español estándar
    "button:has-text('Apply')",  # Inglés simple
    "button:has-text('Postular')",  # Latinoamérica
    "button:has-text('Postularme')",
    "button.jobs-apply-button",  # Clase específica de LinkedIn
    "button[data-job-id]",  # Botón con job ID
    "button[aria-label*='Apply']",  # ARIA label
    "button[aria-label*='Solicitar']",
    "button[aria-label*='Postular']",
)
LINKEDIN_NEXT_SELECTORS = (
    "button:has-text('Next')",
    "button:has-text('Review')",
    "button:has-text('Continue')",
    "button:has-text('Siguiente')",
    "button:has-text('Revisar')",
    "button:has-text('Continuar')",
)
LINKEDIN_SUBMIT_SELECTORS = (
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button:has-text('Enviar solicitud')",
    "button:has-text('Enviar')",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _markdown_to_text(markdown: str) -> str:
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", markdown or "")
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"`{1,3}", "", cleaned)
    cleaned = re.sub(r"^[#>*-]+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[*_]", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _profile_links(perfil: PerfilMaestro) -> dict[str, str]:
    return {_normalize(key): value for key, value in perfil.links.items() if value}


def _first_link(links: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = links.get(_normalize(key), "").strip()
        if value:
            return value
    return ""


def _new_result(oferta: OfertaTrabajo, ats: str) -> ResultadoAplicacion:
    result = ResultadoAplicacion(
        enviado=False,
        metodo="browser_sniper",
        plataforma=oferta.plataforma or ats,
        url_final=oferta.url,
        mensaje="",
    )
    result.detalles["ats"] = ats
    return result


def _finalize_result(
    result: ResultadoAplicacion,
    page: Page | None,
    *,
    enviado: bool,
    mensaje: str,
) -> ResultadoAplicacion:
    result.enviado = enviado
    result.mensaje = mensaje
    if page is not None:
        result.url_final = page.url
    return result


def _detect_ats(url: str) -> str:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if any(token in host for token in ("greenhouse.io", "grnh.se", "grnhse.com")):
        return "greenhouse"
    if "lever.co" in host or "jobs.lever" in host:
        return "lever"
    if "linkedin.com" in host:
        return "linkedin"
    if "getonbrd.com" in host:
        return "getonbrd"
    if any(token in path for token in ("/applications/new", "/apply")):
        return "unsupported"
    return "unsupported"


def _direct_apply_url(url: str, ats: str) -> str:
    clean = url.split("?", 1)[0].rstrip("/")
    if ats == "greenhouse" and not clean.endswith("/applications/new"):
        return f"{clean}/applications/new"
    if ats == "lever" and not clean.endswith("/apply"):
        return f"{clean}/apply"
    return url


def _ordered_contexts(page: Page, frame_hints: Sequence[str] = ()) -> list[PlaywrightContext]:
    contexts: list[PlaywrightContext] = [page]
    prioritized: list[PlaywrightContext] = []
    others: list[PlaywrightContext] = []
    main_frame = getattr(page, "main_frame", None)

    # Greenhouse y otros ATS suelen renderizar el formulario real dentro de iframes
    # controlados por el propio proveedor, así que inspeccionamos esos frames primero.
    for frame in getattr(page, "frames", []):
        if frame is main_frame:
            continue
        frame_url = _normalize(getattr(frame, "url", ""))
        if frame_hints and any(token in frame_url for token in frame_hints):
            prioritized.append(frame)
        else:
            others.append(frame)

    contexts.extend(prioritized)
    contexts.extend(others)
    return contexts


def _find_greenhouse_frame(page: Page) -> Frame | None:
    for frame in getattr(page, "frames", []):
        frame_url = _normalize(getattr(frame, "url", ""))
        if "greenhouse.io" in frame_url or "grnhse.com" in frame_url:
            return frame
    return None


async def _wait_for_selector_safe(context: PlaywrightContext, selector: str) -> bool:
    try:
        await context.wait_for_selector(
            selector,
            state="attached",
            timeout=SELECTOR_TIMEOUT_MS,
        )
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False


async def _wait_for_form_context(
    page: Page,
    selectors: Sequence[str],
    *,
    frame_hints: Sequence[str] = (),
) -> PlaywrightContext | None:
    for context in _ordered_contexts(page, frame_hints):
        for selector in selectors:
            if await _wait_for_selector_safe(context, selector):
                return context
    return None


async def _find_first_locator_in_context(
    context: PlaywrightContext,
    selectors: Sequence[str],
    *,
    visible_only: bool,
) -> Locator | None:
    for selector in selectors:
        if not await _wait_for_selector_safe(context, selector):
            continue
        locator = context.locator(selector).first
        if visible_only:
            try:
                if not await locator.is_visible():
                    continue
            except Exception:
                continue
        return locator
    return None


async def _find_locator(
    page: Page,
    selectors: Sequence[str],
    *,
    frame_hints: Sequence[str] = (),
    visible_only: bool = False,
    preferred_context: PlaywrightContext | None = None,
) -> tuple[PlaywrightContext | None, Locator | None]:
    contexts: list[PlaywrightContext] = []
    if preferred_context is not None:
        contexts.append(preferred_context)
    for context in _ordered_contexts(page, frame_hints):
        if context not in contexts:
            contexts.append(context)

    for context in contexts:
        locator = await _find_first_locator_in_context(
            context,
            selectors,
            visible_only=visible_only,
        )
        if locator is not None:
            return context, locator

    return None, None


async def _fill_locator(locator: Locator, value: str) -> bool:
    try:
        await locator.scroll_into_view_if_needed(timeout=SHORT_TIMEOUT_MS)
    except Exception:
        pass

    try:
        await locator.fill(value, timeout=SHORT_TIMEOUT_MS)
        return True
    except Exception:
        try:
            await locator.click(timeout=SHORT_TIMEOUT_MS)
            await locator.fill(value, timeout=SHORT_TIMEOUT_MS)
            return True
        except Exception:
            return False


async def _fill_first(
    page: Page,
    selectors: Sequence[str],
    value: str,
    *,
    frame_hints: Sequence[str] = (),
    preferred_context: PlaywrightContext | None = None,
) -> bool:
    if not value.strip():
        return False

    _context, locator = await _find_locator(
        page,
        selectors,
        frame_hints=frame_hints,
        preferred_context=preferred_context,
    )
    if locator is None:
        return False

    return await _fill_locator(locator, value)


async def _click_locator(locator: Locator) -> bool:
    try:
        await locator.scroll_into_view_if_needed(timeout=SHORT_TIMEOUT_MS)
    except Exception:
        pass

    try:
        await locator.click(timeout=SHORT_TIMEOUT_MS)
        return True
    except Exception:
        try:
            await locator.click(force=True, timeout=SHORT_TIMEOUT_MS)
            return True
        except Exception:
            return False


async def _click_first(
    page: Page,
    selectors: Sequence[str],
    *,
    frame_hints: Sequence[str] = (),
    preferred_context: PlaywrightContext | None = None,
) -> bool:
    _context, locator = await _find_locator(
        page,
        selectors,
        frame_hints=frame_hints,
        visible_only=True,
        preferred_context=preferred_context,
    )
    if locator is None:
        return False
    return await _click_locator(locator)


async def _active_page(page: Page) -> Page:
    open_pages = [candidate for candidate in page.context.pages if not candidate.is_closed()]
    active = open_pages[-1] if open_pages else page
    try:
        await active.wait_for_load_state("domcontentloaded", timeout=SHORT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass
    return active


async def _settle_page(page: Page) -> Page:
    page = await _active_page(page)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=SHORT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_timeout(750)
    return page


async def _set_hidden_input_files(locator: Locator, file_path: Path) -> bool:
    # Los ATS suelen esconder el <input type="file"> y estilizar un botón falso.
    # Evitamos el click visual y escribimos sobre el input real; si el CSS lo
    # bloquea, lo hacemos visible temporalmente con JS.
    try:
        await locator.set_input_files(str(file_path), timeout=SHORT_TIMEOUT_MS)
        return True
    except Exception:
        pass

    try:
        await locator.evaluate(
            """el => {
                el.hidden = false;
                el.removeAttribute("hidden");
                el.style.display = "block";
                el.style.visibility = "visible";
                el.style.opacity = "1";
                el.style.pointerEvents = "auto";
                el.style.width = "1px";
                el.style.height = "1px";
            }"""
        )
        await locator.set_input_files(str(file_path), timeout=SHORT_TIMEOUT_MS)
        return True
    except Exception as exc:
        logger.debug("No se pudo subir {} con set_input_files: {}", file_path, exc)
        return False


async def _upload_file(
    page: Page,
    selectors: Sequence[str],
    file_path: Path | None,
    *,
    frame_hints: Sequence[str] = (),
    preferred_context: PlaywrightContext | None = None,
) -> bool:
    if file_path is None or not file_path.exists():
        return False

    _context, locator = await _find_locator(
        page,
        selectors,
        frame_hints=frame_hints,
        preferred_context=preferred_context,
    )
    if locator is None:
        return False

    return await _set_hidden_input_files(locator, file_path)


async def _check_all_matching(
    page: Page,
    selectors: Sequence[str],
    *,
    frame_hints: Sequence[str] = (),
    preferred_context: PlaywrightContext | None = None,
) -> int:
    contexts: list[PlaywrightContext] = []
    if preferred_context is not None:
        contexts.append(preferred_context)
    for context in _ordered_contexts(page, frame_hints):
        if context not in contexts:
            contexts.append(context)

    checked = 0
    for context in contexts:
        for selector in selectors:
            if not await _wait_for_selector_safe(context, selector):
                continue
            locators = context.locator(selector)
            try:
                count = await locators.count()
            except Exception:
                continue

            for idx in range(count):
                locator = locators.nth(idx)
                try:
                    if await locator.is_checked():
                        continue
                except Exception:
                    pass
                try:
                    await locator.check(force=True, timeout=SHORT_TIMEOUT_MS)
                    checked += 1
                except Exception:
                    continue
    return checked


async def _page_text(page: Page) -> str:
    if not await _wait_for_selector_safe(page, "body"):
        return ""
    try:
        body = await page.locator("body").inner_text()
    except Exception:
        return ""
    return _normalize(body)


async def _confirm_submission(
    page: Page,
    *,
    form_selectors: Sequence[str],
    success_tokens: Sequence[str],
    frame_hints: Sequence[str] = (),
) -> tuple[bool, str]:
    page = await _settle_page(page)
    body = await _page_text(page)
    url = _normalize(page.url)

    if any(token in body for token in success_tokens):
        return True, "Postulación enviada."
    if any(token in url for token in ("submitted", "thank", "thanks", "success")):
        return True, "Postulación enviada."

    form_context = await _wait_for_form_context(
        page,
        form_selectors,
        frame_hints=frame_hints,
    )
    if form_context is None and body:
        if not any(token in body for token in ("required", "error", "invalid", "complete this field")):
            return True, "Postulación enviada sin confirmación textual."

    return False, "El formulario siguió visible o sin confirmación verificable."


async def _open_greenhouse_form(page: Page) -> tuple[Page, PlaywrightContext | None]:
    form_context = await _wait_for_form_context(
        page,
        GREENHOUSE_FORM_SELECTORS,
        frame_hints=GREENHOUSE_FRAME_HINTS,
    )
    if form_context is not None:
        return page, form_context

    direct_url = _direct_apply_url(page.url, "greenhouse")
    if direct_url != page.url:
        try:
            await page.goto(
                direct_url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS,
            )
            page = await _settle_page(page)
        except PlaywrightTimeoutError:
            logger.debug("Greenhouse direct apply timeout for {}", direct_url)

        form_context = await _wait_for_form_context(
            page,
            GREENHOUSE_FORM_SELECTORS,
            frame_hints=GREENHOUSE_FRAME_HINTS,
        )
        if form_context is not None:
            return page, form_context

    if await _click_first(page, GREENHOUSE_OPEN_SELECTORS, frame_hints=GREENHOUSE_FRAME_HINTS):
        page = await _settle_page(page)
        form_context = await _wait_for_form_context(
            page,
            GREENHOUSE_FORM_SELECTORS,
            frame_hints=GREENHOUSE_FRAME_HINTS,
        )
        if form_context is not None:
            return page, form_context

    return page, None


async def _open_lever_form(page: Page) -> tuple[Page, PlaywrightContext | None]:
    form_context = await _wait_for_form_context(
        page,
        LEVER_FORM_SELECTORS,
        frame_hints=LEVER_FRAME_HINTS,
    )
    if form_context is not None:
        return page, form_context

    direct_url = _direct_apply_url(page.url, "lever")
    if direct_url != page.url:
        try:
            await page.goto(
                direct_url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS,
            )
            page = await _settle_page(page)
        except PlaywrightTimeoutError:
            logger.debug("Lever direct apply timeout for {}", direct_url)

        form_context = await _wait_for_form_context(
            page,
            LEVER_FORM_SELECTORS,
            frame_hints=LEVER_FRAME_HINTS,
        )
        if form_context is not None:
            return page, form_context

    if await _click_first(page, LEVER_OPEN_SELECTORS, frame_hints=LEVER_FRAME_HINTS):
        page = await _settle_page(page)
        form_context = await _wait_for_form_context(
            page,
            LEVER_FORM_SELECTORS,
            frame_hints=LEVER_FRAME_HINTS,
        )
        if form_context is not None:
            return page, form_context

    return page, None


async def _fill_greenhouse_fields(
    page: Page,
    form_context: PlaywrightContext,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    details: dict[str, str],
) -> None:
    target_frame = _find_greenhouse_frame(page)
    if target_frame is not None:
        form_context = target_frame

    first_name, last_name = _split_name(perfil.nombre)
    links = _profile_links(perfil)

    field_map = (
        ("first_name", ("input[name='first_name']", "#first_name"), first_name),
        ("last_name", ("input[name='last_name']", "#last_name"), last_name),
        ("email", ("input[name='email']", "#email", "input[type='email']"), perfil.email),
        ("phone", ("input[name='phone']", "#phone", "input[type='tel']"), perfil.telefono),
        (
            "location",
            ("#auto_complete_input", "input[name='location']", "input[id*='location']"),
            perfil.ubicacion_actual,
        ),
        (
            "linkedin",
            ("input[name*='linkedin']", "input[id*='linkedin']"),
            _first_link(links, "linkedin"),
        ),
        (
            "github",
            ("input[name*='github']", "input[id*='github']"),
            _first_link(links, "github"),
        ),
        (
            "website",
            ("input[name*='portfolio']", "input[name*='website']", "input[id*='website']"),
            _first_link(links, "portfolio", "website", "web"),
        ),
        (
            "cover_letter_text",
            ("textarea[name='cover_letter']", "#cover_letter", "textarea[id*='cover_letter']"),
            cover_letter_text,
        ),
    )

    for detail_key, selectors, value in field_map:
        if await _fill_first(
            page,
            selectors,
            value,
            frame_hints=GREENHOUSE_FRAME_HINTS,
            preferred_context=form_context,
        ):
            details[detail_key] = "filled"

    if await _upload_file(
        page,
        (
            "input[type='file'][name='resume']",
            "input[type='file'][id*='resume']",
            "input[type='file'][name*='resume']",
        ),
        cv_pdf,
        frame_hints=GREENHOUSE_FRAME_HINTS,
        preferred_context=form_context,
    ):
        details["resume"] = "uploaded"

    if await _upload_file(
        page,
        (
            "input[type='file'][name='cover_letter']",
            "input[type='file'][name*='cover']",
            "input[type='file'][id*='cover']",
        ),
        cover_letter_pdf,
        frame_hints=GREENHOUSE_FRAME_HINTS,
        preferred_context=form_context,
    ):
        details["cover_letter_file"] = "uploaded"


async def _fill_lever_fields(
    page: Page,
    form_context: PlaywrightContext,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    details: dict[str, str],
) -> None:
    links = _profile_links(perfil)

    field_map = (
        ("name", ("input[name='name']", "#name"), perfil.nombre),
        ("email", ("input[name='email']", "input[type='email']"), perfil.email),
        ("phone", ("input[name='phone']", "input[type='tel']"), perfil.telefono),
        (
            "location",
            ("input[name='location']", "input[id*='location']"),
            perfil.ubicacion_actual,
        ),
        (
            "linkedin",
            ("input[name='urls[LinkedIn]']", "input[name*='linkedin']"),
            _first_link(links, "linkedin"),
        ),
        (
            "github",
            ("input[name='urls[Github]']", "input[name*='github']"),
            _first_link(links, "github"),
        ),
        (
            "portfolio",
            (
                "input[name='urls[Portfolio]']",
                "input[name*='portfolio']",
                "input[name*='website']",
            ),
            _first_link(links, "portfolio", "website", "web"),
        ),
        (
            "comments",
            ("textarea[name='comments']", "textarea[name='additional_info']", "textarea"),
            cover_letter_text,
        ),
    )

    for detail_key, selectors, value in field_map:
        if await _fill_first(
            page,
            selectors,
            value,
            frame_hints=LEVER_FRAME_HINTS,
            preferred_context=form_context,
        ):
            details[detail_key] = "filled"

    if await _upload_file(
        page,
        (
            "input[type='file'][name='resume']",
            "input[type='file'][name='resume[]']",
            "input[type='file'][name*='resume']",
            "input[type='file'][data-qa='resume-upload-input']",
        ),
        cv_pdf,
        frame_hints=LEVER_FRAME_HINTS,
        preferred_context=form_context,
    ):
        details["resume"] = "uploaded"

    if await _upload_file(
        page,
        (
            "input[type='file'][name='coverLetter']",
            "input[type='file'][name*='cover']",
        ),
        cover_letter_pdf,
        frame_hints=LEVER_FRAME_HINTS,
        preferred_context=form_context,
    ):
        details["cover_letter_file"] = "uploaded"


async def _fill_getonbrd_fields(
    page: Page,
    form_context: PlaywrightContext,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    details: dict[str, str],
) -> None:
    first_name, last_name = _split_name(perfil.nombre)
    links = _profile_links(perfil)

    field_map = (
        ("first_name", ("input[name*='first']", "input[id*='first']"), first_name),
        ("last_name", ("input[name*='last']", "input[id*='last']"), last_name),
        ("name", ("input[name='name']", "input[name*='full_name']"), perfil.nombre),
        ("email", ("input[name='email']", "input[type='email']"), perfil.email),
        ("phone", ("input[name='phone']", "input[type='tel']"), perfil.telefono),
        (
            "linkedin",
            ("input[name*='linkedin']", "input[id*='linkedin']"),
            _first_link(links, "linkedin"),
        ),
        (
            "github",
            ("input[name*='github']", "input[id*='github']"),
            _first_link(links, "github"),
        ),
        (
            "portfolio",
            ("input[name*='portfolio']", "input[name*='website']", "input[id*='website']"),
            _first_link(links, "portfolio", "website", "web"),
        ),
        ("cover_letter_text", ("textarea",), cover_letter_text),
    )

    for detail_key, selectors, value in field_map:
        if await _fill_first(
            page,
            selectors,
            value,
            frame_hints=GETONBRD_FRAME_HINTS,
            preferred_context=form_context,
        ):
            details[detail_key] = "filled"

    if await _upload_file(
        page,
        (
            "input[type='file'][name*='resume']",
            "input[type='file'][name*='cv']",
            "input[type='file']",
        ),
        cv_pdf,
        frame_hints=GETONBRD_FRAME_HINTS,
        preferred_context=form_context,
    ):
        details["resume"] = "uploaded"

    if await _upload_file(
        page,
        (
            "input[type='file'][name*='cover']",
            "input[type='file'][id*='cover']",
        ),
        cover_letter_pdf,
        frame_hints=GETONBRD_FRAME_HINTS,
        preferred_context=form_context,
    ):
        details["cover_letter_file"] = "uploaded"


async def _fill_fallback_fields(
    page: Page,
    form_context: PlaywrightContext,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    details: dict[str, str],
) -> None:
    first_name, last_name = _split_name(perfil.nombre)
    links = _profile_links(perfil)

    field_map = (
        ("first_name", ("input[name*='first']", "input[id*='first']"), first_name),
        ("last_name", ("input[name*='last']", "input[id*='last']"), last_name),
        ("name", ("input[name*='name']",), perfil.nombre),
        ("email", ("input[type='email']", "input[name*='email']"), perfil.email),
        ("phone", ("input[type='tel']", "input[name*='phone']"), perfil.telefono),
        (
            "linkedin",
            ("input[name*='linkedin']", "input[id*='linkedin']"),
            _first_link(links, "linkedin"),
        ),
        (
            "portfolio",
            ("input[name*='portfolio']", "input[name*='website']"),
            _first_link(links, "portfolio", "website", "web"),
        ),
        ("cover_letter_text", ("textarea",), cover_letter_text),
    )

    for detail_key, selectors, value in field_map:
        if await _fill_first(page, selectors, value, preferred_context=form_context):
            details[detail_key] = "filled"

    if await _upload_file(
        page,
        ("input[type='file'][name*='resume']", "input[type='file']"),
        cv_pdf,
        preferred_context=form_context,
    ):
        details["resume"] = "uploaded"

    if await _upload_file(
        page,
        ("input[type='file'][name*='cover']",),
        cover_letter_pdf,
        preferred_context=form_context,
    ):
        details["cover_letter_file"] = "uploaded"


async def _apply_greenhouse(
    page: Page,
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    result = _new_result(oferta, "greenhouse")

    try:
        trace("Greenhouse: buscando formulario")
        page, form_context = await _open_greenhouse_form(page)
        if form_context is None:
            trace("Greenhouse: formulario no disponible")
            return _finalize_result(
                result,
                page,
                enviado=False,
                mensaje="Greenhouse no expuso el formulario a tiempo.",
            )

        if form_context is not page:
            result.detalles["form_iframe"] = "true"
            result.detalles["iframe_url"] = getattr(form_context, "url", "")
            trace("Greenhouse: formulario dentro de iframe")

        for step in range(1, MAX_MULTI_STEP_ATTEMPTS + 1):
            result.detalles["step"] = str(step)
            trace(f"Greenhouse: rellenando campos (paso {step})")
            await _fill_greenhouse_fields(
                page,
                form_context,
                perfil,
                cv_pdf,
                cover_letter_pdf,
                cover_letter_text,
                result.detalles,
            )

            checked = await _check_all_matching(
                page,
                GREENHOUSE_CONSENT_SELECTORS,
                frame_hints=GREENHOUSE_FRAME_HINTS,
                preferred_context=form_context,
            )
            if checked:
                result.detalles["consents_checked"] = str(checked)
                trace(f"Greenhouse: consentimientos activados ({checked})")

            if await _click_first(
                page,
                GREENHOUSE_SUBMIT_SELECTORS,
                frame_hints=GREENHOUSE_FRAME_HINTS,
                preferred_context=form_context,
            ):
                trace("Greenhouse: submit presionado")
                page = await _settle_page(page)
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=GREENHOUSE_FORM_SELECTORS,
                    success_tokens=(
                        "application submitted",
                        "thank you",
                        "thanks for applying",
                    ),
                    frame_hints=GREENHOUSE_FRAME_HINTS,
                )
                trace("Greenhouse: confirmacion recibida" if enviado else "Greenhouse: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

            if not await _click_first(
                page,
                GREENHOUSE_NEXT_SELECTORS,
                frame_hints=GREENHOUSE_FRAME_HINTS,
                preferred_context=form_context,
            ):
                trace("Greenhouse: no se encontro boton Next/Continue")
                return _finalize_result(
                    result,
                    page,
                    enviado=False,
                    mensaje="Greenhouse no mostró un botón compatible para avanzar o enviar.",
                )

            trace("Greenhouse: avanzando al siguiente paso")
            page = await _settle_page(page)
            form_context = await _wait_for_form_context(
                page,
                GREENHOUSE_FORM_SELECTORS,
                frame_hints=GREENHOUSE_FRAME_HINTS,
            )
            if form_context is None:
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=GREENHOUSE_FORM_SELECTORS,
                    success_tokens=(
                        "application submitted",
                        "thank you",
                        "thanks for applying",
                    ),
                    frame_hints=GREENHOUSE_FRAME_HINTS,
                )
                trace("Greenhouse: confirmacion recibida" if enviado else "Greenhouse: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

        trace("Greenhouse: pasos maximos alcanzados")
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje="Greenhouse requiere más pasos de los soportados por el agente.",
        )
    except Exception as exc:
        logger.exception("Fallo Greenhouse auto-apply para {}: {}", oferta.url, exc)
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje=f"Fallo el flujo Greenhouse: {exc}",
        )


async def _apply_lever(
    page: Page,
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    result = _new_result(oferta, "lever")

    try:
        trace("Lever: buscando formulario")
        page, form_context = await _open_lever_form(page)
        if form_context is None:
            trace("Lever: formulario no disponible")
            return _finalize_result(
                result,
                page,
                enviado=False,
                mensaje="Lever no expuso el formulario a tiempo.",
            )

        if form_context is not page:
            result.detalles["form_iframe"] = "true"
            result.detalles["iframe_url"] = getattr(form_context, "url", "")
            trace("Lever: formulario dentro de iframe")

        for step in range(1, MAX_MULTI_STEP_ATTEMPTS + 1):
            result.detalles["step"] = str(step)
            trace(f"Lever: rellenando campos (paso {step})")
            await _fill_lever_fields(
                page,
                form_context,
                perfil,
                cv_pdf,
                cover_letter_pdf,
                cover_letter_text,
                result.detalles,
            )

            checked = await _check_all_matching(
                page,
                LEVER_CONSENT_SELECTORS,
                frame_hints=LEVER_FRAME_HINTS,
                preferred_context=form_context,
            )
            if checked:
                result.detalles["consents_checked"] = str(checked)
                trace(f"Lever: consentimientos activados ({checked})")

            if await _click_first(
                page,
                LEVER_SUBMIT_SELECTORS,
                frame_hints=LEVER_FRAME_HINTS,
                preferred_context=form_context,
            ):
                trace("Lever: submit presionado")
                page = await _settle_page(page)
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=LEVER_FORM_SELECTORS,
                    success_tokens=(
                        "application submitted",
                        "thanks for applying",
                        "your application has been submitted",
                    ),
                    frame_hints=LEVER_FRAME_HINTS,
                )
                trace("Lever: confirmacion recibida" if enviado else "Lever: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

            if not await _click_first(
                page,
                LEVER_NEXT_SELECTORS,
                frame_hints=LEVER_FRAME_HINTS,
                preferred_context=form_context,
            ):
                trace("Lever: no se encontro boton Next/Continue")
                return _finalize_result(
                    result,
                    page,
                    enviado=False,
                    mensaje="Lever no mostró un botón compatible para avanzar o enviar.",
                )

            trace("Lever: avanzando al siguiente paso")
            page = await _settle_page(page)
            form_context = await _wait_for_form_context(
                page,
                LEVER_FORM_SELECTORS,
                frame_hints=LEVER_FRAME_HINTS,
            )
            if form_context is None:
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=LEVER_FORM_SELECTORS,
                    success_tokens=(
                        "application submitted",
                        "thanks for applying",
                        "your application has been submitted",
                    ),
                    frame_hints=LEVER_FRAME_HINTS,
                )
                trace("Lever: confirmacion recibida" if enviado else "Lever: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

        trace("Lever: pasos maximos alcanzados")
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje="Lever requiere más pasos de los soportados por el agente.",
        )
    except Exception as exc:
        logger.exception("Fallo Lever auto-apply para {}: {}", oferta.url, exc)
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje=f"Fallo el flujo Lever: {exc}",
        )


async def _apply_getonbrd(
    page: Page,
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    result = _new_result(oferta, "getonbrd")

    try:
        trace("GetOnBrd: buscando formulario")
        form_context = await _wait_for_form_context(
            page,
            GETONBRD_FORM_SELECTORS,
            frame_hints=GETONBRD_FRAME_HINTS,
        )

        if form_context is None:
            if not await _click_first(page, GETONBRD_OPEN_SELECTORS):
                trace("GetOnBrd: no se encontro CTA para postular")
                return _finalize_result(
                    result,
                    page,
                    enviado=False,
                    mensaje="Get on Board no mostró un botón de postulación compatible.",
                )
            page = await _settle_page(page)
            form_context = await _wait_for_form_context(
                page,
                GETONBRD_FORM_SELECTORS,
                frame_hints=GETONBRD_FRAME_HINTS,
            )

        routed_ats = _detect_ats(page.url)
        if routed_ats == "greenhouse":
            trace("GetOnBrd: redireccion a Greenhouse")
            return await _apply_greenhouse(
                page,
                oferta,
                perfil,
                cv_pdf,
                cover_letter_pdf,
                cover_letter_text,
                trace,
            )
        if routed_ats == "lever":
            trace("GetOnBrd: redireccion a Lever")
            return await _apply_lever(
                page,
                oferta,
                perfil,
                cv_pdf,
                cover_letter_pdf,
                cover_letter_text,
                trace,
            )

        if form_context is None:
            fallback_result = await _apply_fallback(
                page,
                oferta,
                perfil,
                cv_pdf,
                cover_letter_pdf,
                cover_letter_text,
                trace,
            )
            fallback_result.detalles["origin"] = "getonbrd"
            return fallback_result

        trace("GetOnBrd: rellenando campos")
        await _fill_getonbrd_fields(
            page,
            form_context,
            perfil,
            cv_pdf,
            cover_letter_pdf,
            cover_letter_text,
            result.detalles,
        )

        if not await _click_first(
            page,
            GETONBRD_SUBMIT_SELECTORS,
            frame_hints=GETONBRD_FRAME_HINTS,
            preferred_context=form_context,
        ):
            trace("GetOnBrd: no se encontro submit")
            return _finalize_result(
                result,
                page,
                enviado=False,
                mensaje="Get on Board no mostró un botón final de envío.",
            )

        trace("GetOnBrd: submit presionado")
        page = await _settle_page(page)
        enviado, mensaje = await _confirm_submission(
            page,
            form_selectors=GETONBRD_FORM_SELECTORS,
            success_tokens=(
                "postulación enviada",
                "aplicación enviada",
                "thank you",
                "thanks for applying",
            ),
            frame_hints=GETONBRD_FRAME_HINTS,
        )
        trace("GetOnBrd: confirmacion recibida" if enviado else "GetOnBrd: sin confirmacion")
        return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)
    except Exception as exc:
        logger.exception("Fallo Get on Board auto-apply para {}: {}", oferta.url, exc)
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje=f"Fallo el flujo Get on Board: {exc}",
        )


async def _apply_fallback(
    page: Page,
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    result = _new_result(oferta, "fallback")
    result.detalles["fallback"] = "true"

    try:
        form_context = await _wait_for_form_context(page, FALLBACK_FORM_SELECTORS)
        if form_context is None:
            trace("Fallback: no se detecto formulario compatible")
            return _finalize_result(
                result,
                page,
                enviado=False,
                mensaje="No se detectó un formulario simple compatible.",
            )

        for step in range(1, 3):
            result.detalles["step"] = str(step)
            trace(f"Fallback: rellenando campos (paso {step})")
            await _fill_fallback_fields(
                page,
                form_context,
                perfil,
                cv_pdf,
                cover_letter_pdf,
                cover_letter_text,
                result.detalles,
            )

            if await _click_first(page, FALLBACK_SUBMIT_SELECTORS, preferred_context=form_context):
                trace("Fallback: submit presionado")
                page = await _settle_page(page)
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=FALLBACK_FORM_SELECTORS,
                    success_tokens=(
                        "thank you",
                        "application submitted",
                        "postulación enviada",
                    ),
                )
                trace("Fallback: confirmacion recibida" if enviado else "Fallback: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

            if not await _click_first(page, FALLBACK_NEXT_SELECTORS, preferred_context=form_context):
                trace("Fallback: no se encontro Next/Continue")
                return _finalize_result(
                    result,
                    page,
                    enviado=False,
                    mensaje="El fallback no encontró un botón seguro para continuar o enviar.",
                )

            trace("Fallback: avanzando al siguiente paso")
            page = await _settle_page(page)
            form_context = await _wait_for_form_context(page, FALLBACK_FORM_SELECTORS)
            if form_context is None:
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=FALLBACK_FORM_SELECTORS,
                    success_tokens=(
                        "thank you",
                        "application submitted",
                        "postulación enviada",
                    ),
                )
                trace("Fallback: confirmacion recibida" if enviado else "Fallback: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

        trace("Fallback: pasos maximos alcanzados")
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje="El fallback agotó los pasos permitidos sin confirmar el envío.",
        )
    except Exception as exc:
        logger.exception("Fallo fallback auto-apply para {}: {}", oferta.url, exc)
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje=f"Fallo el fallback defensivo: {exc}",
        )


async def _apply_linkedin(
    page: Page,
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    result = _new_result(oferta, "linkedin")

    try:
        trace("LinkedIn: buscando boton Easy Apply")
        
        # Intentar con selectores estáticos primero (timeout corto para fallar rápido)
        button_found = False
        for selector in LINKEDIN_EASY_APPLY_SELECTORS:
            try:
                locator = page.locator(selector).first
                # Timeout corto de 3 segundos por selector
                await locator.wait_for(state="visible", timeout=3000)
                await locator.click(timeout=3000)
                button_found = True
                trace(f"LinkedIn: botón encontrado con selector estático: {selector[:50]}")
                break
            except Exception:
                continue
        
        # Si no encontró con selectores estáticos, usar análisis inteligente
        if not button_found:
            trace("LinkedIn: selectores estáticos fallaron, usando análisis inteligente de DOM")
            from jober.agents.smart_button_finder import click_apply_button_smart
            
            success, message = await click_apply_button_smart(page)
            
            # Si el análisis de DOM también falló, usar VISIÓN como último recurso
            if not success:
                trace("LinkedIn: análisis de DOM falló, usando VISIÓN (GLM-4V)")
                from jober.agents.vision_button_finder import find_and_click_with_vision
                
                vision_success, vision_message = await find_and_click_with_vision(page)
                if not vision_success:
                    return _finalize_result(
                        result,
                        page,
                        enviado=False,
                        mensaje=f"LinkedIn: {vision_message}",
                    )
                trace(f"LinkedIn: botón encontrado con VISIÓN - {vision_message}")
            else:
                trace(f"LinkedIn: botón encontrado con análisis inteligente - {message}")

        page = await _settle_page(page)
        
        # Detectar qué tipo de aplicación se abrió
        trace("LinkedIn: detectando tipo de aplicación")
        
        # Opción 1: Modal de Easy Apply
        form_context = await _wait_for_form_context(page, LINKEDIN_FORM_SELECTORS)
        
        if form_context is None:
            # Opción 2: Redirección a página externa o aplicación normal
            trace("LinkedIn: no es Easy Apply modal, verificando redirección")
            
            # Verificar si cambió la URL (redirección externa)
            current_url = page.url
            if "linkedin.com/jobs" not in current_url.lower():
                trace(f"LinkedIn: redirigido a sitio externo: {current_url}")
                # Detectar ATS del sitio externo
                external_ats = _detect_ats(current_url)
                if external_ats != "unsupported":
                    trace(f"LinkedIn: sitio externo es {external_ats}, delegando")
                    return await _route_apply(
                        page, external_ats, oferta, perfil, cv_pdf, cover_letter_pdf, cover_letter_text, trace
                    )
                else:
                    # Sitio externo desconocido, usar fallback genérico
                    trace("LinkedIn: sitio externo desconocido, usando fallback genérico")
                    return await _apply_fallback(
                        page, oferta, perfil, cv_pdf, cover_letter_pdf, cover_letter_text, trace
                    )
            
            # Opción 3: Página de aplicación de LinkedIn (no modal)
            trace("LinkedIn: buscando formulario en página completa")
            
            # Buscar formulario genérico
            generic_form_selectors = (
                "form",
                "div[role='main']",
                "main",
                "div.jobs-apply",
                "div[class*='apply']",
            )
            
            form_context = await _wait_for_form_context(page, generic_form_selectors, frame_hints=())
            
            if form_context is None:
                # No hay formulario visible, intentar con universal form filler
                trace("LinkedIn: no se encontró formulario estándar, usando análisis universal")
                
                # Verificar si requiere login
                login_required = await page.locator("text=/sign in|log in|iniciar sesión/i").count() > 0
                if login_required:
                    return _finalize_result(
                        result,
                        page,
                        enviado=False,
                        mensaje="LinkedIn requiere iniciar sesión para aplicar.",
                    )
                
                # Verificar si la oferta expiró
                expired = await page.locator("text=/expired|no longer|ya no está|expiró/i").count() > 0
                if expired:
                    return _finalize_result(
                        result,
                        page,
                        enviado=False,
                        mensaje="La oferta de LinkedIn ya no está disponible o expiró.",
                    )
                
                # Intentar con universal form filler
                from jober.agents.universal_form_filler import analyze_and_fill_form, find_and_click_submit
                
                trace("LinkedIn: intentando rellenar formulario con análisis LLM universal")
                fill_result = await analyze_and_fill_form(page, perfil, cv_pdf)
                
                if fill_result["success"]:
                    trace(f"LinkedIn: rellenados {fill_result['filled']}/{fill_result['total']} campos")
                    result.detalles["universal_fill"] = f"{fill_result['filled']}/{fill_result['total']}"
                    
                    # Intentar submit
                    if await find_and_click_submit(page):
                        trace("LinkedIn: formulario enviado con universal filler")
                        page = await _settle_page(page)
                        
                        # Verificar confirmación
                        enviado, mensaje = await _confirm_submission(
                            page,
                            form_selectors=generic_form_selectors,
                            success_tokens=("submitted", "applied", "thank", "success", "enviado", "gracias"),
                        )
                        return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)
                    else:
                        return _finalize_result(
                            result,
                            page,
                            enviado=False,
                            mensaje="LinkedIn: formulario rellenado pero no se encontró botón de envío.",
                        )
                else:
                    return _finalize_result(
                        result,
                        page,
                        enviado=False,
                        mensaje="LinkedIn no expuso formulario de aplicación.",
                    )

        first_name, last_name = _split_name(perfil.nombre)
        field_map = (
            ("first_name", ("input[name*='first']",), first_name),
            ("last_name", ("input[name*='last']",), last_name),
            ("email", ("input[type='email']", "input[name*='email']"), perfil.email),
            ("phone", ("input[type='tel']", "input[name*='phone']"), perfil.telefono),
            ("cover_letter_text", ("textarea",), cover_letter_text),
        )

        for step in range(1, MAX_MULTI_STEP_ATTEMPTS + 1):
            trace(f"LinkedIn: rellenando campos (paso {step})")
            for detail_key, selectors, value in field_map:
                if await _fill_first(page, selectors, value, preferred_context=form_context):
                    result.detalles[detail_key] = "filled"

            if await _upload_file(
                page,
                ("input[type='file']", "input[name*='resume']", "input[name*='cv']"),
                cv_pdf,
                preferred_context=form_context,
            ):
                result.detalles["resume"] = "uploaded"

            if await _click_first(page, LINKEDIN_SUBMIT_SELECTORS, preferred_context=form_context):
                trace("LinkedIn: submit presionado")
                page = await _settle_page(page)
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=LINKEDIN_FORM_SELECTORS,
                    success_tokens=("application submitted", "applied", "submitted", "thanks"),
                )
                trace("LinkedIn: confirmacion recibida" if enviado else "LinkedIn: sin confirmacion")
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

            if not await _click_first(page, LINKEDIN_NEXT_SELECTORS, preferred_context=form_context):
                return _finalize_result(
                    result,
                    page,
                    enviado=False,
                    mensaje="LinkedIn no mostró botones Next/Review/Submit.",
                )

            trace("LinkedIn: avanzando al siguiente paso")
            page = await _settle_page(page)
            form_context = await _wait_for_form_context(page, LINKEDIN_FORM_SELECTORS)
            if form_context is None:
                enviado, mensaje = await _confirm_submission(
                    page,
                    form_selectors=LINKEDIN_FORM_SELECTORS,
                    success_tokens=("application submitted", "applied", "submitted", "thanks"),
                )
                return _finalize_result(result, page, enviado=enviado, mensaje=mensaje)

        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje="LinkedIn requiere más pasos de los soportados por el agente.",
        )
    except Exception as exc:
        logger.exception("Fallo LinkedIn auto-apply para {}: {}", oferta.url, exc)
        return _finalize_result(
            result,
            page,
            enviado=False,
            mensaje=f"Fallo el flujo LinkedIn: {exc}",
        )


async def _apply_universal_agent(
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_md: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    """Agente Universal usando browser-use para ATS desconocidos.
    
    Este agente usa visión y árboles de accesibilidad para navegar
    dinámicamente cualquier formulario de aplicación.
    """
    result = _new_result(oferta, "universal_agent")
    
    if not BROWSER_USE_AVAILABLE:
        return _finalize_result(
            result,
            None,
            enviado=False,
            mensaje="browser-use no está instalado. Ejecuta: pip install browser-use",
        )
    
    trace("Iniciando Agente Universal con browser-use")
    
    try:
        # Preparar información del perfil para el prompt
        trace(f"Preparando información del perfil: {perfil.nombre}")
        
        experiencias_list = perfil.experiencias if perfil.experiencias else []
        trace(f"Experiencias: {type(experiencias_list)}, len={len(experiencias_list)}")
        
        experiencias_text = "\n".join([
            f"- {exp.cargo} en {exp.empresa} ({exp.fecha_inicio} - {exp.fecha_fin or 'Presente'})"
            for exp in (experiencias_list[:3] if isinstance(experiencias_list, list) else [])
        ]) if experiencias_list else "No especificado"
        
        educacion_list = perfil.educacion if perfil.educacion else []
        educacion_text = "\n".join([
            f"- {edu.titulo} en {edu.institucion} ({edu.fecha_fin or 'En curso'})"
            for edu in educacion_list[:2]
        ]) if educacion_list else "No especificado"
        
        habilidades_list = perfil.habilidades_tecnicas if perfil.habilidades_tecnicas else []
        habilidades_text = ", ".join(habilidades_list[:10]) if habilidades_list else "No especificado"
        
        # Links puede ser dict o list
        links_dict = perfil.links if perfil.links else {}
        if isinstance(links_dict, dict):
            links_text = "\n".join([
                f"- {tipo}: {url}"
                for tipo, url in list(links_dict.items())[:3]
            ]) if links_dict else "No especificado"
        else:
            # Si es lista de objetos Link
            links_text = "\n".join([
                f"- {link.tipo}: {link.url}"
                for link in links_dict[:3]
            ]) if links_dict else "No especificado"
        
        # Crear el task prompt con toda la información del candidato
        task_prompt = f"""Eres un asistente de aplicación de empleo. Tu ÚNICO objetivo es completar el formulario de aplicación en esta página web.

INFORMACIÓN DEL CANDIDATO:
Nombre completo: {perfil.nombre}
Email: {perfil.email}
Teléfono: {perfil.telefono}
Ubicación: {perfil.ubicacion_actual}
Título profesional: {perfil.titulo_profesional}

Resumen profesional:
{(perfil.resumen[:500] if perfil.resumen else 'No especificado')}

Experiencia laboral:
{experiencias_text}

Educación:
{educacion_text}

Habilidades técnicas:
{habilidades_text}

Links profesionales:
{links_text}

ARCHIVO CV (RUTA ABSOLUTA):
{cv_pdf.absolute()}

INSTRUCCIONES CRÍTICAS:
1. Navega por el formulario de aplicación y rellena TODOS los campos requeridos con la información proporcionada arriba.
2. Cuando encuentres un campo para subir CV/Resume, usa EXACTAMENTE esta ruta: {cv_pdf.absolute()}
3. Si hay campos de texto libre (ej: "Why do you want to work here?", "Cover letter"), escribe una respuesta breve y profesional basada en el resumen del candidato.
4. Marca cualquier checkbox de términos y condiciones si es necesario.
5. Haz clic en el botón de "Submit", "Send Application", "Apply" o similar para enviar la aplicación.
6. DETENTE INMEDIATAMENTE después de ver una pantalla de confirmación que diga "Application submitted", "Thank you", "Success" o similar.
7. NO navegues a otras páginas después de enviar la aplicación.
8. Si encuentras errores de validación, intenta corregirlos usando la información del candidato.

IMPORTANTE: Tu objetivo es COMPLETAR y ENVIAR la aplicación. No te detengas hasta que veas la confirmación de éxito."""

        trace(f"Configurando browser-use con modelo de visión")
        
        # browser-use requiere configuración específica del LLM
        # Usar la configuración de settings directamente
        from jober.core.config import load_settings
        from langchain_openai import ChatOpenAI
        
        settings = load_settings()
        
        # Crear LLM compatible con browser-use
        # browser-use funciona mejor con modelos de OpenAI o compatibles
        llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0.1,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        
        trace(f"LLM configurado: {settings.llm_model}")
        
        # Crear agente con browser-use
        # Browser se crea automáticamente por el agente
        agent = Agent(
            task=task_prompt,
            llm=llm,
        )
        
        trace(f"Navegando a {oferta.url}")
        
        # Ejecutar el agente
        agent_result = await agent.run(start_url=oferta.url)
        
        trace("Agente universal completó su ejecución")
        
        # Parsear resultado
        # browser-use devuelve un objeto con información sobre la ejecución
        success = False
        mensaje = "Agente universal ejecutado"
        
        # Verificar si el agente completó exitosamente
        if agent_result:
            # El agente devuelve información sobre las acciones tomadas
            final_message = str(agent_result.final_result()) if hasattr(agent_result, 'final_result') else str(agent_result)
            
            # Buscar indicadores de éxito en el resultado
            success_indicators = [
                "submitted", "success", "thank you", "application sent",
                "enviado", "éxito", "gracias", "aplicación enviada"
            ]
            
            if any(indicator in final_message.lower() for indicator in success_indicators):
                success = True
                mensaje = "Aplicación enviada exitosamente por agente universal"
            else:
                mensaje = f"Agente universal completó pero no se detectó confirmación clara: {final_message[:200]}"
        
        trace(f"Resultado: {'Éxito' if success else 'Incierto'}")
        
        return _finalize_result(
            result,
            None,
            enviado=success,
            mensaje=mensaje,
        )
        
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.exception("Fallo agente universal para {}: {}", oferta.url, exc)
        trace(f"Error en agente universal: {exc}")
        trace(f"Traceback completo: {tb}")
        return _finalize_result(
            result,
            None,
            enviado=False,
            mensaje=f"Fallo el agente universal: {exc}",
        )


async def _route_apply(
    page: Page,
    ats: str,
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None,
    cover_letter_text: str,
    trace: TraceFn,
) -> ResultadoAplicacion:
    if ats == "greenhouse":
        return await _apply_greenhouse(
            page,
            oferta,
            perfil,
            cv_pdf,
            cover_letter_pdf,
            cover_letter_text,
            trace,
        )
    if ats == "lever":
        return await _apply_lever(
            page,
            oferta,
            perfil,
            cv_pdf,
            cover_letter_pdf,
            cover_letter_text,
            trace,
        )
    if ats == "linkedin":
        return await _apply_linkedin(
            page,
            oferta,
            perfil,
            cv_pdf,
            cover_letter_pdf,
            cover_letter_text,
            trace,
        )
    if ats == "getonbrd":
        return _finalize_result(
            _new_result(oferta, "getonbrd"),
            page,
            enviado=False,
            mensaje="Requiere sesión activa. Postulación manual recomendada.",
        )

    # ATS desconocido - usar agente universal con browser-use
    if ats == "unsupported":
        trace("ATS desconocido detectado, delegando a agente universal")
        # Cerrar la página de Playwright ya que browser-use manejará su propio navegador
        await page.close()
        
        # Llamar al agente universal (no necesita cover_letter_text, usa cover_letter_md)
        return await _apply_universal_agent(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_pdf,
            cover_letter_pdf=cover_letter_pdf,
            cover_letter_md=cover_letter_text,  # Pasar el texto como markdown
            trace=trace,
        )
    
    # Fallback por si acaso
    manual = _new_result(oferta, "unsupported")
    return _finalize_result(
        manual,
        page,
        enviado=False,
        mensaje="ATS no reconocido y agente universal no disponible.",
    )


async def auto_apply_to_job(
    oferta: OfertaTrabajo,
    perfil: PerfilMaestro,
    cv_pdf: Path,
    cover_letter_pdf: Path | None = None,
    cover_letter_md: str = "",
) -> ResultadoAplicacion:
    """Auto-apply dirigido por ATS con Playwright async."""
    ats = _detect_ats(oferta.url)
    result = _new_result(oferta, ats)
    trace_seq = 0

    def _trace(message: str) -> None:
        nonlocal trace_seq
        trace_seq += 1
        result.detalles[f"trace_{trace_seq:02d}"] = message
        print(f"[auto-apply] {message}")

    if not oferta.url:
        return _finalize_result(
            result,
            None,
            enviado=False,
            mensaje="La oferta no tiene URL.",
        )
    if not cv_pdf.exists():
        return _finalize_result(
            result,
            None,
            enviado=False,
            mensaje="No existe el PDF del CV adaptado para subir.",
        )
    if not perfil.nombre or not perfil.email:
        return _finalize_result(
            result,
            None,
            enviado=False,
            mensaje="Faltan datos mínimos del perfil para auto-aplicar (nombre y email).",
        )
    
    # Si es unsupported, delegar directamente al agente universal sin Playwright
    if ats == "unsupported":
        _trace(f"ATS detectado: {ats} (desconocido)")
        _trace("Delegando a agente universal con browser-use")
        
        cover_letter_text = _markdown_to_text(cover_letter_md)
        
        return await _apply_universal_agent(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_pdf,
            cover_letter_pdf=cover_letter_pdf,
            cover_letter_md=cover_letter_text,
            trace=_trace,
        )

    cover_letter_text = _markdown_to_text(cover_letter_md)
    _trace(f"ATS detectado: {ats}")

    try:
        async with async_playwright() as playwright:
            executable_path = Path(playwright.chromium.executable_path)
            if not executable_path.exists():
                return _finalize_result(
                    result,
                    None,
                    enviado=False,
                    mensaje="Playwright no tiene navegador instalado. Ejecuta: playwright install chromium",
                )
            try:
                _trace("Lanzando navegador Playwright")
                browser = await playwright.chromium.launch(headless=False, slow_mo=50)
            except PermissionError:
                return _finalize_result(
                    result,
                    None,
                    enviado=False,
                    mensaje=(
                        "Playwright no pudo lanzar el navegador por permisos. "
                        "Reabre la terminal como Administrador o ajusta el antivirus."
                    ),
                )
            except PlaywrightError as exc:
                if "executable doesn't exist" in str(exc).lower():
                    return _finalize_result(
                        result,
                        None,
                        enviado=False,
                        mensaje="Playwright no tiene navegador instalado. Ejecuta: playwright install chromium",
                    )
                return _finalize_result(
                    result,
                    None,
                    enviado=False,
                    mensaje=f"Fallo Playwright al lanzar el navegador: {exc}",
                )
            try:
                profile_id = get_active_profile_id()
                paths = ensure_profile_dirs(profile_id)
                storage_state_path = paths.profile_dir / "playwright_storage.json"
                context = await browser.new_context(
                    user_agent=REALISTIC_USER_AGENT,
                    viewport={"width": 1440, "height": 1600},
                    storage_state=str(storage_state_path) if storage_state_path.exists() else None,
                )
                page = await context.new_page()
                try:
                    _trace("Abriendo URL de oferta")
                    await page.goto(
                        oferta.url,
                        wait_until="domcontentloaded",
                        timeout=NAVIGATION_TIMEOUT_MS,
                    )
                except PlaywrightTimeoutError:
                    return _finalize_result(
                        result,
                        page,
                        enviado=False,
                        mensaje="La página del ATS no cargó a tiempo.",
                    )

                _trace("URL cargada, iniciando flujo ATS")
                page = await _settle_page(page)
                resultado = await _route_apply(
                    page,
                    ats,
                    oferta,
                    perfil,
                    cv_pdf,
                    cover_letter_pdf,
                    cover_letter_text,
                    _trace,
                )
                try:
                    await context.storage_state(path=str(storage_state_path))
                    _trace("Sesion persistida en storage_state")
                except Exception:
                    pass
                return resultado
            finally:
                await browser.close()
    except Exception as exc:
        logger.exception("Fallo auto-apply para {}: {}", oferta.url, exc)
        return _finalize_result(
            result,
            None,
            enviado=False,
            mensaje=f"Fallo el auto-apply: {exc}",
        )

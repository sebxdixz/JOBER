"""CLI principal de Jober - comandos init, apply, stats."""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji/unicode support
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from langchain_core.messages import HumanMessage
from playwright.async_api import async_playwright

from jober.core.config import (
    JOBER_HOME,
    JOBER_ENV_FILE,
    ensure_profile_dirs,
    get_active_profile_id,
    list_profile_ids,
    normalize_profile_id,
    resolve_profile_id,
    set_active_profile_id,
    load_settings,
)
from jober.core.models import RegistroPostulacion, EstadoPostulacion
from jober.core.state import JoberState, new_state, view_state
from jober.agents.cv_reader import extract_text_from_cvs
from jober.agents.auto_apply import auto_apply_to_job
from jober.agents.autonomous_search import find_new_leads_by_platform, lead_to_oferta
from jober.agents.offer_evaluator import evaluate_offer, evaluate_offer_for_scout
from jober.agents.orchestrator import build_init_graph, build_apply_graph
from jober.cli.preferences_flow import run_preferences_flow
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.utils.file_io import (
    ensure_job_output_dir,
    load_last_scout,
    load_perfil_maestro,
    save_application_output,
    save_last_scout,
    save_perfil_maestro,
    write_output_artifact,
)
from jober.utils.runtime_status import update_status, upsert_job
from jober.utils.status_server import start_status_server, stop_status_server
from jober.utils.tracking import add_record, get_stats, read_all_records
from jober.cli.autonomous import autonomous_run_loop

app = typer.Typer(
    name="jober",
    help="Jober CLI - Multiagente LangGraph para postulaciones laborales.",
    no_args_is_help=True,
)
profile_app = typer.Typer(
    name="profile",
    help=(
        "Gestion de perfiles (multi-profile).\n\n"
        "Ejemplos:\n"
        "  jober profile list\n"
        "  jober profile create data\n"
        "  jober profile create --id ai-remote --copy-from default\n"
        "  jober profile use data\n"
        "  jober profile info --profile data"
    ),
    no_args_is_help=True,
)
console = Console(force_terminal=True)


def _estado_from_application_result(enviado: bool, mensaje: str) -> EstadoPostulacion:
    if enviado:
        return EstadoPostulacion.APLICADO
    if any(
        marker in mensaje
        for marker in [
            "Formulario con campos requeridos no soportados.",
            "No se encontro un boton de envio compatible.",
            "No existe el PDF del CV adaptado para subir.",
        ]
    ):
        return EstadoPostulacion.PREPARADO
    return EstadoPostulacion.FALLIDO


def _coerce_profile_id(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    candidate = raw_value.strip()
    if not candidate or not any(char.isalnum() for char in candidate):
        return None
    return normalize_profile_id(candidate)


def _resolve_profile_id_input(
    profile_id: str | None,
    option_value: str | None,
    *,
    prompt_text: str,
) -> str:
    resolved = _coerce_profile_id(option_value) or _coerce_profile_id(profile_id)
    while resolved is None:
        resolved = _coerce_profile_id(Prompt.ask(prompt_text))
        if resolved is None:
            console.print("[yellow]Ingresa un ID valido usando letras, numeros, '-' o '_' .[/yellow]")
    return resolved


def _linkedin_storage_state_path(profile_id: str) -> Path:
    paths = ensure_profile_dirs(profile_id)
    return paths.profile_dir / "playwright_storage.json"


def _build_ai_remote_preferences(existing: PreferenciasLaborales | None = None) -> PreferenciasLaborales:
    prefs = existing.model_copy(deep=True) if existing is not None else PreferenciasLaborales()
    prefs.roles_deseados = [
        "AI Engineer",
        "LLM Engineer",
        "ML Engineer",
        "MLOps Engineer",
        "AI Ops",
        "LLM Ops",
        "Data Scientist",
        "Data Analyst",
        "AI Automation Engineer",
    ]
    prefs.nivel_experiencia = prefs.nivel_experiencia or "mid"
    prefs.anos_experiencia = max(prefs.anos_experiencia, 2)
    prefs.resumen_candidato = (
        "Engineer focused on AI systems, LLM orchestration, automation and production-ready backend workflows."
    )
    prefs.habilidades_dominadas = list(dict.fromkeys(
        prefs.habilidades_dominadas + [
            "Python", "LangGraph", "Pydantic", "Docker", "Kubernetes",
            "PostgreSQL", "RESTful APIs", "LLMs", "RAGs", "Automation",
        ]
    ))
    prefs.habilidades_en_aprendizaje = list(dict.fromkeys(
        prefs.habilidades_en_aprendizaje + ["MLOps", "CI/CD", "AWS", "GCP", "Azure"]
    ))
    prefs.habilidades_must_have = ["Python", "Machine Learning", "LLMs", "Automation"]
    prefs.habilidades_nice_to_have = ["LangGraph", "Docker", "Kubernetes", "RAG", "MLOps"]
    prefs.herramientas_y_tecnologias = list(dict.fromkeys(
        prefs.herramientas_y_tecnologias + [
            "Python", "LangGraph", "Pydantic", "Docker", "Kubernetes", "PostgreSQL", "Git", "Linux"
        ]
    ))
    prefs.industrias_preferidas = ["AI", "Tech", "Automation", "SaaS", "FinTech"]
    prefs.tipo_empresa = ["startup", "corporativo", "pyme"]
    prefs.modalidad = ["remoto", "remote"]
    prefs.ubicaciones = ["Remote", "Remoto"]
    prefs.paises_permitidos = ["Remote", "Remoto"]
    prefs.paises_excluidos = []
    prefs.disponibilidad = prefs.disponibilidad or "inmediata"
    prefs.jornada = "full-time"
    prefs.salario_minimo = prefs.salario_minimo or "1600 USD liquido"
    prefs.salario_ideal = prefs.salario_ideal or "2500 USD liquido"
    prefs.moneda_preferida = prefs.moneda_preferida or "USD"
    prefs.acepta_negociar_salario = True
    prefs.min_match_score = max(prefs.min_match_score, 0.55)
    prefs.aplicar_sin_100_requisitos = True
    prefs.max_anos_experiencia_extra = max(prefs.max_anos_experiencia_extra, 3)
    prefs.abierto_a_roles_similares = True
    prefs.deal_breakers = ["presencial", "hibrido obligatorio", "menos de 1600 USD liquido"]
    prefs.idiomas_requeridos = ["Espanol", "Ingles"]
    prefs.motivacion = (
        "Busco roles remotos de AI, LLM, ML engineering y automatizacion donde pueda construir agentes y sistemas productivos."
    )
    prefs.fortalezas_clave = [
        "LangGraph", "arquitecturas multiagente", "orquestacion de LLMs", "automatizacion", "backend con Python"
    ]
    prefs.areas_mejora = ["MLOps a gran escala", "cloud hyperscalers"]
    prefs.plataformas_activas = ["getonbrd", "linkedin", "meetfrank"]
    prefs.max_aplicaciones_por_dia = max(prefs.max_aplicaciones_por_dia, 10)
    prefs.delay_entre_aplicaciones_segundos = max(prefs.delay_entre_aplicaciones_segundos, 60)
    return prefs


async def _run_init_flow(graph, state: JoberState):
    """Ejecuta el flujo de init con loop interactivo de onboarding."""
    result = await graph.ainvoke(state)

    while result.get("next_step") == "wait_user_input":
        last_msg = result.get("messages", [])[-1] if result.get("messages") else None
        if last_msg:
            console.print(f"\n[bold cyan]Jober:[/bold cyan] {last_msg.content}")

        user_input = Prompt.ask("[yellow]Tu respuesta[/yellow]")

        if user_input.lower() in ("skip", "saltar", "fin"):
            result["next_step"] = "merge_profile"

        result["messages"] = result.get("messages", []) + [HumanMessage(content=user_input)]
        result = await graph.ainvoke(result)

    return view_state(result)


@app.command()
def init(
    profile: str | None = typer.Option(None, "--profile", "-p", help="ID del perfil a crear/usar"),
):
    """Inicializar Jober: configurar API key, subir CVs y crear perfil maestro."""
    profile_id = set_active_profile_id(profile or get_active_profile_id())
    paths = ensure_profile_dirs(profile_id)

    console.print(Panel.fit(
        f"[bold cyan]Bienvenido a Jober[/bold cyan]\nPerfil activo: {profile_id}",
        border_style="cyan",
    ))

    # 1. API Key
    settings = load_settings()
    if not settings.llm_api_key:
        api_key = Prompt.ask(
            "[yellow]Ingresa tu API Key (Z.AI)[/yellow]",
            password=True,
        )
        base_url = Prompt.ask(
            "[yellow]Base URL del LLM[/yellow]",
            default="https://api.z.ai/api/coding/paas/v4",
        )
        model = Prompt.ask(
            "[yellow]Modelo LLM[/yellow]",
            default="GLM-4.7-flash",
        )
        JOBER_ENV_FILE.write_text(
            f'LLM_API_KEY="{api_key}"\nLLM_BASE_URL="{base_url}"\nLLM_MODEL="{model}"\nLLM_TEMPERATURE=0.2\n',
            encoding="utf-8",
        )
        console.print("[green]API Key guardada en ~/.jober/.env[/green]")
    else:
        console.print("[green]API Key ya configurada.[/green]")

    # 2. CVs
    cv_path_str = Prompt.ask(
        "[yellow]Ruta a la carpeta con tus CVs (PDFs)[/yellow]",
        default=str(paths.cv_base_dir),
    )
    cv_source = Path(cv_path_str).expanduser().resolve()

    if cv_source != paths.cv_base_dir and cv_source.exists():
        for pdf in cv_source.glob("*.pdf"):
            dest = paths.cv_base_dir / pdf.name
            if not dest.exists():
                shutil.copy2(pdf, dest)
                console.print(f"  Copiado: {pdf.name}")

    pdf_count = len(list(paths.cv_base_dir.glob("*.pdf")))
    if pdf_count == 0:
        console.print("[red]No se encontraron PDFs. Coloca tus CVs en la carpeta del perfil.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]{pdf_count} CV(s) encontrado(s).[/green]")

    # 3. Extraer texto y ejecutar grafo init
    console.print("\n[cyan]Analizando tus CVs...[/cyan]")
    cv_text = extract_text_from_cvs(paths.cv_base_dir)

    if not cv_text.strip():
        console.print("[red]No se pudo extraer texto de los PDFs.[/red]")
        raise typer.Exit(1)

    init_graph = build_init_graph()
    state = new_state(cv_raw_text=cv_text)

    result = asyncio.run(_run_init_flow(init_graph, state))

    if result.error:
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)

    # 4. Onboarding de preferencias laborales
    console.print("\n[cyan]Ahora vamos a configurar tus preferencias de busqueda...[/cyan]")
    console.print("[dim]Responde en lenguaje natural. Puedes ser informal.[/dim]\n")

    preferences_result = asyncio.run(run_preferences_flow(result.perfil))

    if preferences_result.get("error"):
        console.print(f"[yellow]No se pudieron configurar preferencias: {preferences_result['error']}[/yellow]")
        console.print("[dim]Puedes configurarlas manualmente editando el perfil maestro.[/dim]")
    else:
        result.perfil = preferences_result["perfil"]

    if not result.perfil.email:
        result.perfil.email = Prompt.ask("[yellow]Email para postulaciones[/yellow]")
    if not result.perfil.telefono:
        result.perfil.telefono = Prompt.ask("[yellow]Telefono para postulaciones[/yellow]", default="")
    if not result.perfil.ubicacion_actual:
        result.perfil.ubicacion_actual = Prompt.ask("[yellow]Ubicacion actual[/yellow]", default="")

    save_perfil_maestro(result.perfil, profile_id)
    console.print(Panel.fit(
        f"[bold green]Perfil guardado en {paths.perfil_path}[/bold green]\n\n"
        f"Nombre: {result.perfil.nombre}\n"
        f"Titulo: {result.perfil.titulo_profesional}\n"
        f"Habilidades: {len(result.perfil.habilidades_tecnicas)} tecnicas, {len(result.perfil.habilidades_blandas)} blandas\n"
        f"Experiencias: {len(result.perfil.experiencias)}\n\n"
        f"[cyan]Preferencias de busqueda:[/cyan]\n"
        f"  Roles: {', '.join(result.perfil.preferencias.roles_deseados[:3]) or 'No especificado'}\n"
        f"  Match minimo: {result.perfil.preferencias.min_match_score:.0%}\n"
        f"  Max aplicaciones/dia: {result.perfil.preferencias.max_aplicaciones_por_dia}\n\n"
        f"[bold yellow]Siguiente paso:[/bold yellow]\n"
        f"  jober scout --limit 5",
        border_style="green",
    ))


@app.command()
def apply(
    url: str = typer.Argument(..., help="URL de la oferta de trabajo"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Postular a una oferta: scrapea, analiza y genera CV adaptado + cover letter."""
    profile_id = resolve_profile_id(profile)
    perfil = load_perfil_maestro(profile_id)
    if perfil is None:
        console.print("[red]No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Procesando oferta[/bold cyan]\n{url}\nPerfil: {profile_id}",
        border_style="cyan",
    ))

    if "linkedin.com/jobs/view/" in url:
        storage_state_path = _linkedin_storage_state_path(profile_id)
        if not storage_state_path.exists():
            console.print(Panel.fit(
                "[bold yellow]LinkedIn requiere sesion activa.[/bold yellow]\n"
                "Ejecuta primero: jober login linkedin --profile "
                f"{profile_id}",
                border_style="yellow",
            ))
            raise typer.Exit(1)

    apply_graph = build_apply_graph()
    state = new_state(job_url=url, perfil=perfil)

    result = asyncio.run(_run_apply_flow(apply_graph, state))

    output_dir = ensure_job_output_dir(
        profile_id,
        result.oferta if result.oferta else None,
        url=url,
        plataforma=result.oferta.plataforma if result.oferta else "",
        empresa=result.oferta.empresa if result.oferta else "",
        cargo=result.oferta.titulo if result.oferta else "",
    )

    write_output_artifact(output_dir, "apply_trace.json", {
        "job_url": url,
        "profile_id": profile_id,
        "timestamp": datetime.now().isoformat(),
        "error": result.error,
        "should_apply": result.should_apply,
        "screening_notes": result.screening_notes,
        "oferta": result.oferta.model_dump(),
        "match_score": result.documentos.match_score,
    })

    if result.error:
        console.print(f"[red]Error: {result.error}[/red]")
        console.print(f"[dim]Traza guardada en: {output_dir}[/dim]")
        raise typer.Exit(1)

    if not result.should_apply:
        notes = "\n".join(f"- {note}" for note in result.screening_notes) or "- Oferta filtrada"
        console.print(Panel.fit(
            f"[bold yellow]Oferta filtrada antes de generar documentos[/bold yellow]\n\n{notes}\n\nTraza guardada en:\n  {output_dir}",
            border_style="yellow",
        ))
        raise typer.Exit(0)

    output_dir = save_application_output(
        result.oferta,
        result.documentos,
        profile_id=profile_id,
        output_dir=output_dir,
    )
    application_result = asyncio.run(
        auto_apply_to_job(
            result.oferta,
            result.perfil,
            output_dir / "cv_adaptado.pdf",
            cover_letter_pdf=output_dir / "cover_letter.pdf",
            cover_letter_md=result.documentos.cover_letter_md,
        )
    )
    result.resultado_aplicacion = application_result
    save_application_output(
        result.oferta,
        result.documentos,
        application_result,
        profile_id=profile_id,
        output_dir=output_dir,
    )

    estado = _estado_from_application_result(application_result.enviado, application_result.mensaje)

    record = RegistroPostulacion(
        empresa=result.oferta.empresa,
        cargo=result.oferta.titulo,
        plataforma=result.oferta.plataforma,
        url=url,
        estado=estado,
        carpeta_output=str(output_dir),
        notas=application_result.mensaje,
    )
    add_record(record, profile_id)

    console.print(Panel.fit(
        f"[bold green]Postulacion procesada[/bold green]\n\n"
        f"Empresa: {result.oferta.empresa}\n"
        f"Cargo: {result.oferta.titulo}\n"
        f"Ubicacion: {result.oferta.ubicacion}\n"
        f"Match Score: {result.documentos.match_score:.0%}\n"
        f"Analisis: {result.documentos.analisis_fit}\n\n"
        f"Resultado auto-apply: {'Enviado' if application_result.enviado else 'No enviado'}\n"
        f"Estado: {application_result.mensaje}\n\n"
        f"Archivos guardados en:\n  {output_dir}",
        border_style="green",
    ))


async def _run_apply_flow(graph, state: JoberState):
    """Ejecuta el flujo de apply."""
    return view_state(await graph.ainvoke(state))


@app.command()
def stats(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Ver estadisticas de postulaciones."""
    profile_id = resolve_profile_id(profile)
    data = get_stats(profile_id)

    if data["total"] == 0:
        console.print("[yellow]Aun no hay postulaciones registradas.[/yellow]")
        return

    table = Table(title=f"Estadisticas de Postulaciones ({profile_id})")
    table.add_column("Metrica", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("Total postulaciones", str(data["total"]))

    for estado, count in data["por_estado"].items():
        table.add_row(f"  - {estado}", str(count))

    if data["por_plataforma"]:
        table.add_row("", "")
        for platform, count in data["por_plataforma"].items():
            table.add_row(f"{platform}", str(count))

    console.print(table)


async def _login_with_playwright(storage_state_path: Path, provider: str) -> None:
    login_url = "https://www.linkedin.com/login"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        try:
            context = await browser.new_context(
                storage_state=str(storage_state_path) if storage_state_path.exists() else None
            )
            page = await context.new_page()
            await page.goto(login_url, wait_until="domcontentloaded")
            await asyncio.to_thread(
                input,
                "Cuando termines el login en el navegador, presiona ENTER aqui...",
            )
            await context.storage_state(path=str(storage_state_path))
        finally:
            await browser.close()


@app.command()
def login(
    provider: str = typer.Argument(..., help="Proveedor de login (linkedin)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Guardar sesion de login para proveedores (LinkedIn)."""
    provider_key = provider.strip().lower()
    if provider_key != "linkedin":
        console.print("[red]Proveedor no soportado. Usa: linkedin[/red]")
        raise typer.Exit(1)

    profile_id = resolve_profile_id(profile)
    paths = ensure_profile_dirs(profile_id)
    storage_state_path = paths.profile_dir / "playwright_storage.json"

    console.print(
        Panel.fit(
            f"[bold cyan]Login {provider_key}[/bold cyan]\n"
            f"Perfil: {profile_id}\n"
            f"Sesion se guardara en: {storage_state_path}",
            border_style="cyan",
        )
    )
    console.print("[yellow]Se abrira un navegador visible. Inicia sesion y vuelve aqui.[/yellow]")
    asyncio.run(_login_with_playwright(storage_state_path, provider_key))
    console.print("[green]Sesion guardada. Puedes correr auto-apply y se reutilizara.[/green]")


@app.command()
def logout(
    provider: str = typer.Argument(..., help="Proveedor de logout (linkedin)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Eliminar sesion persistida (LinkedIn)."""
    provider_key = provider.strip().lower()
    if provider_key != "linkedin":
        console.print("[red]Proveedor no soportado. Usa: linkedin[/red]")
        raise typer.Exit(1)

    profile_id = resolve_profile_id(profile)
    storage_state_path = _linkedin_storage_state_path(profile_id)
    if not storage_state_path.exists():
        console.print("[yellow]No hay sesion guardada para este perfil.[/yellow]")
        return

    storage_state_path.unlink(missing_ok=True)
    console.print("[green]Sesion eliminada.[/green]")


@app.command()
def review(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximo de registros a mostrar"),
):
    """Revisar postulaciones recientes y estado de ofertas."""
    profile_id = resolve_profile_id(profile)
    records = read_all_records(profile_id)
    if not records:
        console.print("[yellow]No hay postulaciones registradas.[/yellow]")
        return

    table = Table(title=f"Postulaciones recientes ({profile_id})")
    table.add_column("Fecha", style="cyan")
    table.add_column("Empresa", style="green")
    table.add_column("Cargo", style="white")
    table.add_column("Estado", style="magenta")
    table.add_column("Notas", style="dim")

    for record in records[: max(limit, 1)]:
        table.add_row(
            record.fecha,
            record.empresa or "-",
            record.cargo or "-",
            record.estado.value if hasattr(record.estado, "value") else str(record.estado),
            (record.notas or "")[:120],
        )

    console.print(table)


@app.command()
def status(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Ver estado de la configuracion de Jober."""
    profile_id = resolve_profile_id(profile)
    paths = ensure_profile_dirs(profile_id)

    console.print(Panel.fit("[bold cyan]Estado de Jober[/bold cyan]", border_style="cyan"))

    checks = {
        "Carpeta ~/.jober/": JOBER_HOME.exists(),
        "API Key configurada": JOBER_ENV_FILE.exists() and load_settings().llm_api_key != "",
        f"Perfil activo: {profile_id}": True,
        "Perfil maestro": paths.perfil_path.exists(),
        "CVs cargados": any(paths.cv_base_dir.glob("*.pdf")) if paths.cv_base_dir.exists() else False,
    }

    for label, ok in checks.items():
        icon = "[green]OK[/green]" if ok else "[red]X[/red]"
        console.print(f"  {icon} {label}")

    console.print(f"\nPerfil JSON: {paths.perfil_path}")
    console.print(f"CVs: {paths.cv_base_dir}")
    console.print(f"Postulaciones: {paths.postulaciones_dir}")


@app.command()
def doctor(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Diagnostico rapido de dependencias y configuracion."""
    profile_id = resolve_profile_id(profile)
    paths = ensure_profile_dirs(profile_id)

    def _check_import(name: str) -> bool:
        try:
            importlib.import_module(name)
            return True
        except Exception:
            return False

    search_provider = os.getenv("JOBER_SEARCH_PROVIDER", "duckduckgo").strip().lower()
    search_key = os.getenv("JOBER_SEARCH_API_KEY", "").strip()
    needs_key = search_provider in {"serper", "serpapi"}

    has_latex = bool(shutil.which("pdflatex") or shutil.which("xelatex"))
    has_playwright = _check_import("playwright")
    has_reportlab = _check_import("reportlab")

    table = Table(title=f"Jober Doctor ({profile_id})")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Notas", style="white")

    table.add_row(
        "API Key",
        "OK" if (JOBER_ENV_FILE.exists() and load_settings().llm_api_key) else "MISSING",
        "Configura con jober init",
    )
    table.add_row(
        "Perfil maestro",
        "OK" if paths.perfil_path.exists() else "MISSING",
        str(paths.perfil_path),
    )
    table.add_row(
        "CVs",
        "OK" if any(paths.cv_base_dir.glob("*.pdf")) else "MISSING",
        str(paths.cv_base_dir),
    )
    table.add_row(
        "ReportLab (PDF fallback)",
        "OK" if has_reportlab else "MISSING",
        "Requerido para PDF sin navegador",
    )
    table.add_row(
        f"Search provider ({search_provider})",
        "OK" if (not needs_key or search_key) else "MISSING",
        "Configura JOBER_SEARCH_API_KEY si usas serper/serpapi",
    )
    table.add_row(
        "Playwright (PDF via Chromium)",
        "OK" if has_playwright else "MISSING",
        "Solo si usas JOBER_PDF_ENGINE=playwright",
    )
    table.add_row(
        "LaTeX (pdflatex/xelatex)",
        "OK" if has_latex else "MISSING",
        "Mejor calidad de CV si esta instalado",
    )

    console.print(table)


@app.command("preset-ai")
def preset_ai(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Aplica un preset para roles AI/LLM/ML remotos al perfil maestro."""
    profile_id = resolve_profile_id(profile)
    perfil = load_perfil_maestro(profile_id)
    if perfil is None:
        console.print("[red]No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        raise typer.Exit(1)

    perfil.preferencias = _build_ai_remote_preferences(perfil.preferencias)
    save_perfil_maestro(perfil, profile_id)

    console.print(Panel.fit(
        "[bold green]Preset AI remoto aplicado[/bold green]\n\n"
        f"Perfil: {profile_id}\n"
        f"Roles: {', '.join(perfil.preferencias.roles_deseados)}\n"
        f"Modalidad: {', '.join(perfil.preferencias.modalidad)}\n"
        f"Salario minimo: {perfil.preferencias.salario_minimo}\n\n"
        "[bold yellow]Siguiente paso:[/bold yellow]\n"
        "  jober scout --limit 5",
        border_style="green",
    ))


@app.command()
def scout(
    limit: int = typer.Option(5, "--limit", "-l", help="Cantidad de ofertas a evaluar"),
    per_platform: int = typer.Option(5, "--per-platform", help="Resultados iniciales por plataforma"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
    ui: bool = typer.Option(True, "--ui/--no-ui", help="Mostrar UI local en vivo"),
    ui_port: int = typer.Option(8765, "--ui-port", help="Puerto de la UI local"),
):
    """Busca y rankea ofertas en vivo sin aplicar automaticamente."""
    profile_id = resolve_profile_id(profile)
    perfil = load_perfil_maestro(profile_id)
    if perfil is None:
        console.print("[red]No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        raise typer.Exit(1)

    server = None
    if ui:
        server = start_status_server(profile_id, port=ui_port)
        if server is None:
            console.print("[yellow]No se pudo iniciar la UI local (puerto ocupado).[/yellow]")
        else:
            console.print(f"[green]UI local: http://127.0.0.1:{ui_port}[/green]")

    update_status(profile_id, mode="scout", stage="searching", message="Buscando ofertas...", jobs=[])

    meetfrank_engine = os.getenv("JOBER_MEETFRANK_ENGINE", "").strip().lower()
    if meetfrank_engine == "playwright" and "meetfrank" in perfil.preferencias.plataformas_activas:
        console.print(
            "[yellow]MeetFrank usa Playwright: mas lento y puede generar costos extra.[/yellow]"
        )

    try:
        fetch_per_platform = max(per_platform * 3, 12)
        grouped_leads = asyncio.run(find_new_leads_by_platform(perfil, max_per_platform=fetch_per_platform))
        counts = {platform: len(leads) for platform, leads in grouped_leads.items()}
        if counts:
            summary = " | ".join(f"{platform}: {count}" for platform, count in counts.items())
            console.print(f"[dim]Leads por plataforma: {summary}[/dim]")
            update_status(
                profile_id,
                stage="ranking",
                message=f"Leads por plataforma: {summary}",
            )

        leads = []
        platform_order = [p for p in ["linkedin", "getonbrd", "meetfrank", "rss"] if p in grouped_leads]
        for idx in range(fetch_per_platform):
            for platform in platform_order:
                platform_leads = grouped_leads.get(platform, [])
                if idx < len(platform_leads):
                    leads.append(platform_leads[idx])

        if not leads:
            save_last_scout({
                "generated_at": datetime.now().isoformat(),
                "limit": limit,
                "per_platform": per_platform,
                "candidates": [],
            }, profile_id)
            console.print("[yellow]No se encontraron ofertas nuevas.[/yellow]")
            raise typer.Exit(0)

        ranked = []
        filtered_reasons: dict[str, int] = {}
        console.print(f"[cyan]Evaluando {len(leads)} ofertas...[/cyan]")
        for lead in leads:
            oferta = lead_to_oferta(lead)
            show_candidate, notes, quick_score = evaluate_offer_for_scout(oferta, perfil)
            if not show_candidate:
                reason = notes[0] if notes else "Filtrada"
                filtered_reasons[reason] = filtered_reasons.get(reason, 0) + 1
                upsert_job(profile_id, {
                    "url": lead.url,
                    "title": oferta.titulo,
                    "company": oferta.empresa,
                    "location": oferta.ubicacion,
                    "platform": oferta.plataforma,
                    "status": "filtered",
                })
                continue
            ranked.append((
                lead,
                quick_score,
                view_state(new_state(
                    job_url=lead.url,
                    perfil=perfil,
                    oferta=oferta,
                    should_apply=True,
                    screening_notes=notes,
                )),
            ))

        ranked.sort(key=lambda item: item[1], reverse=True)
        ranked = ranked[:limit]

        scout_payload = {
            "generated_at": datetime.now().isoformat(),
            "limit": limit,
            "per_platform": per_platform,
            "candidates": [
                {
                    "rank": idx,
                    "url": lead.url,
                    "score": score,
                    "empresa": result.oferta.empresa,
                    "cargo": result.oferta.titulo,
                    "ubicacion": result.oferta.ubicacion,
                    "plataforma": result.oferta.plataforma,
                    "source": getattr(lead, "source", ""),
                    "snippet": getattr(lead, "snippet", ""),
                    "screening_notes": result.screening_notes,
                }
                for idx, (lead, score, result) in enumerate(ranked, 1)
            ],
        }
        save_last_scout(scout_payload, profile_id)

        if not ranked:
            if filtered_reasons:
                summary = " | ".join(f"{reason}: {count}" for reason, count in filtered_reasons.items())
                console.print(f"[dim]Motivos de descarte: {summary}[/dim]")
            console.print("[yellow]No hubo ofertas que pasaran el screening.[/yellow]")
            raise typer.Exit(0)

        table = Table(title=f"Ofertas rankeadas ({profile_id})")
        table.add_column("#", style="cyan", width=3)
        table.add_column("Empresa", style="green")
        table.add_column("Cargo", style="white")
        table.add_column("Match", style="magenta", width=8)
        table.add_column("Ubicacion", style="yellow")
        table.add_column("URL", style="blue")

        for idx, (lead, score, result) in enumerate(ranked, 1):
            upsert_job(profile_id, {
                "url": lead.url,
                "title": result.oferta.titulo,
                "company": result.oferta.empresa,
                "location": result.oferta.ubicacion,
                "platform": result.oferta.plataforma,
                "status": "ranked",
                "score": f"{score:.0%}",
            })
            table.add_row(
                str(idx),
                result.oferta.empresa or "-",
                result.oferta.titulo or "-",
                f"{score:.0%}",
                result.oferta.ubicacion or "-",
                lead.url,
            )

        console.print(table)
        console.print("\n[bold yellow]Para aplicar una:[/bold yellow] `jober apply \"<url>\"`")
        console.print("[bold yellow]Para aplicar desde este scout:[/bold yellow] `jober apply-scout --top 1` o `jober apply-scout --all`")
    finally:
        update_status(profile_id, stage="done", message="Scout finalizado")
        stop_status_server(server)


@app.command("apply-scout")
def apply_scout(
    top: int = typer.Option(1, "--top", help="Aplica a los primeros N resultados del ultimo scout"),
    apply_all: bool = typer.Option(False, "--all", help="Aplica a todos los resultados del ultimo scout"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
):
    """Aplica usando los resultados guardados del ultimo `jober scout`."""
    profile_id = resolve_profile_id(profile)
    perfil = load_perfil_maestro(profile_id)
    if perfil is None:
        console.print("[red]No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        raise typer.Exit(1)

    scout_payload = load_last_scout(profile_id)
    if not scout_payload or not scout_payload.get("candidates"):
        console.print("[yellow]No existe un scouting previo utilizable. Ejecuta `jober scout` primero.[/yellow]")
        raise typer.Exit(0)

    candidates = scout_payload["candidates"]
    if not apply_all:
        candidates = candidates[:top]

    console.print(f"[cyan]Aplicando sobre {len(candidates)} oferta(s) del ultimo scout...[/cyan]")
    for candidate in candidates:
        url = candidate["url"]
        console.print(f"\n[bold cyan]Aplicando:[/bold cyan] {url}")
        apply(url, profile=profile_id)


@app.command()
def run(
    max_iterations: int = typer.Option(None, "--max-iterations", "-n", help="Numero maximo de iteraciones (None = infinito)"),
    per_platform: int = typer.Option(3, "--per-platform", help="Cantidad de ofertas iniciales por plataforma en cada ronda"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a usar (default: activo)"),
    ui: bool = typer.Option(True, "--ui/--no-ui", help="Mostrar UI local en vivo"),
    ui_port: int = typer.Option(8765, "--ui-port", help="Puerto de la UI local"),
    sleep_seconds: int = typer.Option(120, "--sleep", help="Segundos entre iteraciones"),
):
    """Iniciar busqueda autonoma continua de ofertas y aplicacion automatica."""
    profile_id = resolve_profile_id(profile)
    perfil = load_perfil_maestro(profile_id)
    if perfil is None:
        console.print("[red]No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        raise typer.Exit(1)

    asyncio.run(
        autonomous_run_loop(
            max_iterations=max_iterations,
            per_platform=per_platform,
            profile_id=profile_id,
            ui=ui,
            ui_port=ui_port,
            sleep_seconds=sleep_seconds,
        )
    )


@app.command()
def tutorial():
    """Tutorial explicativo en Espanol e Ingles."""
    es = (
        "Jober tutorial (ES)\n"
        "1. Configura tu perfil:\n"
        "   jober init --profile ai\n"
        "2. (Opcional) Preset AI remoto:\n"
        "   jober preset-ai --profile ai\n"
        "3. Scout manual:\n"
        "   jober scout --limit 5 --per-platform 3 --profile ai\n"
        "   UI local (auto-refresh):\n"
        "   jober scout --ui --ui-port 8765\n"
        "4. Aplica a una URL o desde el scout:\n"
        "   jober apply \"<url>\" --profile ai\n"
        "   jober apply-scout --top 2 --profile ai\n"
        "5. Modo autonomo:\n"
        "   jober run --profile ai\n"
        "   UI local (auto-refresh):\n"
        "   jober run --ui --ui-port 8765\n"
        "\n"
        "MeetFrank con Playwright (mas lento / mas costo):\n"
        "   $env:JOBER_MEETFRANK_ENGINE=\"playwright\"\n"
        "Vision mode opcional para formularios dificiles:\n"
        "   $env:JOBER_VISION_MODE=\"1\"\n"
        "\n"
        "Perfiles:\n"
        "   jober profile list\n"
        "   jober profile create data\n"
        "   jober profile use data\n"
        "   jober profile info --profile data\n"
        "\n"
        "Archivos clave:\n"
        "   ~/.jober/profiles/<perfil>/perfil_maestro.json\n"
        "   ~/.jober/profiles/<perfil>/cv_base/\n"
        "   ~/.jober/profiles/<perfil>/postulaciones/\n"
    )
    en = (
        "Jober tutorial (EN)\n"
        "1. Setup your profile:\n"
        "   jober init --profile ai\n"
        "2. (Optional) AI remote preset:\n"
        "   jober preset-ai --profile ai\n"
        "3. Manual scout:\n"
        "   jober scout --limit 5 --per-platform 3 --profile ai\n"
        "   Local UI (auto-refresh):\n"
        "   jober scout --ui --ui-port 8765\n"
        "4. Apply to one URL or from scout:\n"
        "   jober apply \"<url>\" --profile ai\n"
        "   jober apply-scout --top 2 --profile ai\n"
        "5. Autonomous mode:\n"
        "   jober run --profile ai\n"
        "   Local UI (auto-refresh):\n"
        "   jober run --ui --ui-port 8765\n"
        "\n"
        "MeetFrank with Playwright (slower / higher cost):\n"
        "   $env:JOBER_MEETFRANK_ENGINE=\"playwright\"\n"
        "Optional vision mode for difficult forms:\n"
        "   $env:JOBER_VISION_MODE=\"1\"\n"
        "\n"
        "Profiles:\n"
        "   jober profile list\n"
        "   jober profile create data\n"
        "   jober profile use data\n"
        "   jober profile info --profile data\n"
        "\n"
        "Key files:\n"
        "   ~/.jober/profiles/<profile>/perfil_maestro.json\n"
        "   ~/.jober/profiles/<profile>/cv_base/\n"
        "   ~/.jober/profiles/<profile>/postulaciones/\n"
    )
    console.print(Panel.fit(es + "\n" + en, border_style="cyan"))


@profile_app.command("list")
def profile_list():
    """Lista perfiles disponibles."""
    active = get_active_profile_id()
    ensure_profile_dirs(active)
    profiles = list_profile_ids()
    if not profiles:
        console.print("[yellow]No hay perfiles creados aun. Usa `jober init --profile <id>`.[/yellow]")
        return
    table = Table(title="Perfiles")
    table.add_column("ID", style="cyan")
    table.add_column("Activo", style="green")
    for pid in profiles:
        table.add_row(pid, "SI" if pid == active else "")
    console.print(table)


@profile_app.command("use")
def profile_use(
    profile_id: str | None = typer.Argument(None, help="ID del perfil a activar"),
    profile_id_option: str | None = typer.Option(None, "--id", "-i", help="ID del perfil a activar"),
):
    """Activa un perfil existente. Si omites el ID, lo pide por prompt."""
    ensure_profile_dirs(get_active_profile_id())
    existing = list_profile_ids()
    if not existing:
        console.print("[yellow]No hay perfiles creados aun. Usa `jober profile create`.[/yellow]")
        raise typer.Exit(1)
    if profile_id is None and profile_id_option is None:
        console.print(f"Perfiles disponibles: {', '.join(existing)}")
    profile_id = _resolve_profile_id_input(
        profile_id,
        profile_id_option,
        prompt_text="ID del perfil a activar",
    )
    if profile_id not in existing:
        console.print(f"[red]Perfil '{profile_id}' no existe. Usa `jober profile create {profile_id}`.[/red]")
        raise typer.Exit(1)
    set_active_profile_id(profile_id)
    console.print(f"[green]Perfil activo: {profile_id}[/green]")


@profile_app.command("create")
def profile_create(
    profile_id: str | None = typer.Argument(None, help="ID del perfil a crear"),
    profile_id_option: str | None = typer.Option(None, "--id", "-i", help="ID del perfil a crear"),
    copy_from: str | None = typer.Option(None, "--copy-from", help="Clonar perfil base"),
    activate: bool = typer.Option(True, "--activate/--no-activate", help="Activar al crear"),
):
    """Crea un nuevo perfil. Si omites el ID, lo pide por prompt."""
    profile_id = _resolve_profile_id_input(
        profile_id,
        profile_id_option,
        prompt_text="ID del nuevo perfil",
    )
    if profile_id in list_profile_ids():
        console.print(f"[yellow]El perfil '{profile_id}' ya existe.[/yellow]")
        if activate:
            set_active_profile_id(profile_id)
        return

    paths = ensure_profile_dirs(profile_id)

    if copy_from:
        source_id = normalize_profile_id(copy_from)
        if source_id not in list_profile_ids():
            console.print(f"[yellow]Perfil base '{source_id}' no existe. Se crea vacio.[/yellow]")
        else:
            source_paths = ensure_profile_dirs(source_id)
            if source_paths.perfil_path.exists() and not paths.perfil_path.exists():
                shutil.copy2(source_paths.perfil_path, paths.perfil_path)
            if source_paths.cv_base_dir.exists():
                for pdf in source_paths.cv_base_dir.glob("*.pdf"):
                    dest = paths.cv_base_dir / pdf.name
                    if not dest.exists():
                        shutil.copy2(pdf, dest)

    if activate:
        set_active_profile_id(profile_id)

    console.print(f"[green]Perfil creado: {profile_id}[/green]")
    console.print(f"Perfil JSON: {paths.perfil_path}")


@profile_app.command("info")
def profile_info(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Perfil a inspeccionar"),
):
    """Muestra rutas del perfil."""
    profile_id = resolve_profile_id(profile)
    paths = ensure_profile_dirs(profile_id)
    console.print(Panel.fit(
        f"Perfil: {profile_id}\n"
        f"JSON: {paths.perfil_path}\n"
        f"CVs: {paths.cv_base_dir}\n"
        f"Postulaciones: {paths.postulaciones_dir}\n"
        f"Tracking: {paths.tracking_csv}\n"
        f"Last scout: {paths.last_scout_path}",
        border_style="cyan",
    ))


app.add_typer(profile_app, name="profile")


if __name__ == "__main__":
    app()

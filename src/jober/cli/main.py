"""CLI principal de Jober — comandos init, apply, stats."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
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

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from langchain_core.messages import HumanMessage

from jober.core.config import (
    JOBER_HOME,
    JOBER_ENV_FILE,
    CV_BASE_DIR,
    PERFIL_MAESTRO_PATH,
    ensure_jober_dirs,
    load_settings,
)
from jober.core.models import RegistroPostulacion, EstadoPostulacion
from jober.core.state import JoberState
from jober.agents.cv_reader import extract_text_from_cvs
from jober.agents.orchestrator import build_init_graph, build_apply_graph
from jober.utils.file_io import save_perfil_maestro, load_perfil_maestro, save_application_output
from jober.utils.tracking import add_record, get_stats

app = typer.Typer(
    name="jober",
    help="Jober CLI - Multiagente LangGraph para postulaciones laborales.",
    no_args_is_help=True,
)
console = Console(force_terminal=True)


# ── jober init ──────────────────────────────────────────────────────────────

@app.command()
def init():
    """Inicializar Jober: configurar API key, subir CVs y crear perfil maestro."""
    console.print(Panel.fit(
        "[bold cyan]🚀 Bienvenido a Jober[/bold cyan]\n"
        "Vamos a configurar tu perfil profesional.",
        border_style="cyan",
    ))

    ensure_jober_dirs()

    # 1. API Key
    settings = load_settings()
    if not settings.openai_api_key:
        api_key = Prompt.ask(
            "[yellow]🔑 Ingresa tu OpenAI API Key[/yellow]",
            password=True,
        )
        JOBER_ENV_FILE.write_text(
            f'OPENAI_API_KEY="{api_key}"\nLLM_MODEL="gpt-4o"\nLLM_TEMPERATURE=0.2\n',
            encoding="utf-8",
        )
        console.print("[green]✅ API Key guardada en ~/.jober/.env[/green]")
    else:
        console.print("[green]✅ API Key ya configurada.[/green]")

    # 2. CVs
    cv_path_str = Prompt.ask(
        "[yellow]📄 Ruta a la carpeta con tus CVs (PDFs)[/yellow]",
        default=str(CV_BASE_DIR),
    )
    cv_source = Path(cv_path_str).expanduser().resolve()

    if cv_source != CV_BASE_DIR and cv_source.exists():
        for pdf in cv_source.glob("*.pdf"):
            dest = CV_BASE_DIR / pdf.name
            if not dest.exists():
                shutil.copy2(pdf, dest)
                console.print(f"  📋 Copiado: {pdf.name}")

    pdf_count = len(list(CV_BASE_DIR.glob("*.pdf")))
    if pdf_count == 0:
        console.print("[red]⚠️  No se encontraron PDFs. Coloca tus CVs en ~/.jober/cv_base/[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✅ {pdf_count} CV(s) encontrado(s).[/green]")

    # 3. Extraer texto y ejecutar grafo init
    console.print("\n[cyan]🧠 Analizando tus CVs...[/cyan]")
    cv_text = extract_text_from_cvs(CV_BASE_DIR)

    if not cv_text.strip():
        console.print("[red]⚠️  No se pudo extraer texto de los PDFs.[/red]")
        raise typer.Exit(1)

    # Ejecutar el grafo de init (cv_reader → onboarding)
    init_graph = build_init_graph()
    state = JoberState(cv_raw_text=cv_text)

    # Fase 1: CV Reader + primera pregunta de onboarding
    result = asyncio.run(_run_init_flow(init_graph, state))

    if result.error:
        console.print(f"[red]❌ Error: {result.error}[/red]")
        raise typer.Exit(1)

    # Guardar perfil
    save_perfil_maestro(result.perfil)
    console.print(Panel.fit(
        f"[bold green]✅ Perfil maestro guardado en {PERFIL_MAESTRO_PATH}[/bold green]\n"
        f"Nombre: {result.perfil.nombre}\n"
        f"Título: {result.perfil.titulo_profesional}\n"
        f"Habilidades: {len(result.perfil.habilidades_tecnicas)} técnicas, "
        f"{len(result.perfil.habilidades_blandas)} blandas\n"
        f"Experiencias: {len(result.perfil.experiencias)}",
        border_style="green",
    ))


async def _run_init_flow(graph, state: JoberState) -> JoberState:
    """Ejecuta el flujo de init con loop interactivo de onboarding."""
    # Primera ejecución: cv_reader → onboarding (primera pregunta)
    result = await graph.ainvoke(state)

    # Loop interactivo de onboarding
    while result.get("next_step") == "wait_user_input":
        # Mostrar pregunta del agente
        last_msg = result.get("messages", [])[-1] if result.get("messages") else None
        if last_msg:
            console.print(f"\n[bold cyan]🤖 Jober:[/bold cyan] {last_msg.content}")

        # Obtener respuesta del usuario
        user_input = Prompt.ask("[yellow]Tu respuesta[/yellow]")

        if user_input.lower() in ("skip", "saltar", "fin"):
            result["next_step"] = "merge_profile"

        # Continuar el grafo con la respuesta
        result["messages"] = result.get("messages", []) + [HumanMessage(content=user_input)]
        result = await graph.ainvoke(result)

    # Convertir a JoberState si es dict
    if isinstance(result, dict):
        return JoberState(**{k: v for k, v in result.items() if k in JoberState.model_fields})

    return result


# ── jober apply ─────────────────────────────────────────────────────────────

@app.command()
def apply(
    url: str = typer.Argument(..., help="URL de la oferta de trabajo"),
):
    """Postular a una oferta: scrapea, analiza y genera CV adaptado + cover letter."""
    perfil = load_perfil_maestro()
    if perfil is None:
        console.print("[red]⚠️  No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]🎯 Procesando oferta[/bold cyan]\n{url}",
        border_style="cyan",
    ))

    apply_graph = build_apply_graph()
    state = JoberState(job_url=url, perfil=perfil)

    result = asyncio.run(_run_apply_flow(apply_graph, state))

    if isinstance(result, dict):
        result = JoberState(**{k: v for k, v in result.items() if k in JoberState.model_fields})

    if result.error:
        console.print(f"[red]❌ Error: {result.error}[/red]")
        raise typer.Exit(1)

    # Guardar output
    output_dir = save_application_output(result.oferta, result.documentos)

    # Registrar en tracking
    record = RegistroPostulacion(
        empresa=result.oferta.empresa,
        cargo=result.oferta.titulo,
        plataforma=result.oferta.plataforma,
        url=url,
        estado=EstadoPostulacion.APLICADO,
        carpeta_output=str(output_dir),
    )
    add_record(record)

    # Mostrar resultados
    console.print(Panel.fit(
        f"[bold green]✅ Postulación procesada[/bold green]\n\n"
        f"🏢 Empresa: {result.oferta.empresa}\n"
        f"💼 Cargo: {result.oferta.titulo}\n"
        f"📍 Ubicación: {result.oferta.ubicacion}\n"
        f"🎯 Match Score: {result.documentos.match_score:.0%}\n"
        f"📝 Análisis: {result.documentos.analisis_fit}\n\n"
        f"📂 Archivos guardados en:\n   {output_dir}",
        border_style="green",
    ))


async def _run_apply_flow(graph, state: JoberState) -> JoberState:
    """Ejecuta el flujo de apply."""
    return await graph.ainvoke(state)


# ── jober stats ─────────────────────────────────────────────────────────────

@app.command()
def stats():
    """Ver estadísticas de postulaciones."""
    data = get_stats()

    if data["total"] == 0:
        console.print("[yellow]📊 Aún no hay postulaciones registradas.[/yellow]")
        return

    table = Table(title="📊 Estadísticas de Postulaciones")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("Total postulaciones", str(data["total"]))

    for estado, count in data["por_estado"].items():
        table.add_row(f"  └─ {estado}", str(count))

    if data["por_plataforma"]:
        table.add_row("", "")
        for platform, count in data["por_plataforma"].items():
            table.add_row(f"📡 {platform}", str(count))

    console.print(table)


# ── jober status ────────────────────────────────────────────────────────────

@app.command()
def status():
    """Ver estado de la configuración de Jober."""
    console.print(Panel.fit("[bold cyan]🔍 Estado de Jober[/bold cyan]", border_style="cyan"))

    checks = {
        "📁 Carpeta ~/.jober/": JOBER_HOME.exists(),
        "🔑 API Key configurada": JOBER_ENV_FILE.exists() and load_settings().openai_api_key != "",
        "📄 CVs cargados": any(CV_BASE_DIR.glob("*.pdf")) if CV_BASE_DIR.exists() else False,
        "🧠 Perfil maestro": PERFIL_MAESTRO_PATH.exists(),
    }

    for label, ok in checks.items():
        icon = "[green]✅[/green]" if ok else "[red]❌[/red]"
        console.print(f"  {icon} {label}")


if __name__ == "__main__":
    app()

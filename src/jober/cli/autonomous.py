"""Comando jober run — modo autónomo de búsqueda y aplicación continua."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from jober.agents.auto_apply import auto_apply_to_job
from jober.agents.autonomous_search import find_new_opportunities
from jober.agents.orchestrator import build_apply_graph
from jober.core.models import RegistroPostulacion, EstadoPostulacion
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro, save_application_output_async
from jober.utils.tracking import add_record, read_all_records


console = Console()


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


async def autonomous_run_loop(max_iterations: int | None = None):
    """Loop principal de búsqueda y aplicación autónoma."""
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if perfil is None:
        console.print("[red]⚠️  No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        return
    
    prefs = perfil.preferencias
    apply_graph = build_apply_graph()
    console.print(Panel.fit(
        f"[bold cyan]🤖 Modo Autónomo Activado[/bold cyan]\n\n"
        f"Roles: {', '.join(prefs.roles_deseados[:3]) or 'Cualquiera'}\n"
        f"Match mínimo: {prefs.min_match_score:.0%}\n"
        f"Max aplicaciones/día: {prefs.max_aplicaciones_por_dia}\n"
        f"Plataformas: {', '.join(prefs.plataformas_activas)}\n\n"
        f"[yellow]Presiona Ctrl+C para detener[/yellow]",
        border_style="cyan",
    ))
    
    iteration = 0
    aplicaciones_hoy = 0
    ultimo_reset_dia = datetime.now().date()
    
    # Cargar URLs ya procesadas
    records = read_all_records()
    urls_procesadas = {r.url for r in records if r.url}
    
    try:
        while True:
            iteration += 1
            
            # Reset contador diario
            hoy = datetime.now().date()
            if hoy != ultimo_reset_dia:
                aplicaciones_hoy = 0
                ultimo_reset_dia = hoy
            
            # Verificar límite diario
            if aplicaciones_hoy >= prefs.max_aplicaciones_por_dia:
                console.print(f"\n[yellow]⏸️  Límite diario alcanzado ({prefs.max_aplicaciones_por_dia}). Esperando hasta mañana...[/yellow]")
                await asyncio.sleep(3600)  # Esperar 1 hora y revisar
                continue
            
            console.print(f"\n[bold cyan]═══ Iteración {iteration} ═══[/bold cyan]")
            
            # 1. Buscar nuevas ofertas
            console.print("[cyan]🔍 Buscando nuevas ofertas...[/cyan]")
            urls = await find_new_opportunities(perfil, max_per_platform=20)
            
            # Filtrar URLs ya procesadas
            urls_nuevas = [url for url in urls if url not in urls_procesadas]
            
            if not urls_nuevas:
                console.print("[yellow]  No hay ofertas nuevas. Esperando 5 minutos...[/yellow]")
                await asyncio.sleep(300)
                continue
            
            console.print(f"[green]  ✓ {len(urls_nuevas)} ofertas nuevas encontradas[/green]")
            
            # 2. Procesar cada oferta
            for idx, url in enumerate(urls_nuevas, 1):
                if aplicaciones_hoy >= prefs.max_aplicaciones_por_dia:
                    break
                
                console.print(f"\n[cyan]📄 [{idx}/{len(urls_nuevas)}] Analizando: {url[:80]}...[/cyan]")
                
                try:
                    state = JoberState(job_url=url, perfil=perfil)
                    result = await apply_graph.ainvoke(state)

                    if isinstance(result, dict):
                        result = JoberState(**{k: v for k, v in result.items() if k in JoberState.model_fields})

                    if result.error:
                        console.print(f"[red]  ✗ Error en pipeline: {result.error[:100]}[/red]")
                        urls_procesadas.add(url)
                        continue

                    if not result.should_apply:
                        motivo = " | ".join(result.screening_notes[:3])
                        console.print(f"[yellow]  ⊘ Filtrada por screening: {motivo}[/yellow]")
                        urls_procesadas.add(url)
                        continue

                    oferta = result.oferta
                    docs = result.documentos
                    
                    # Verificar match mínimo
                    if docs.match_score < prefs.min_match_score:
                        console.print(f"[yellow]  ⊘ Match bajo ({docs.match_score:.0%} < {prefs.min_match_score:.0%})[/yellow]")
                        urls_procesadas.add(url)
                        continue
                    
                    # Guardar aplicación (Markdown + PDF)
                    output_dir = await save_application_output_async(oferta, docs)
                    application_result = await auto_apply_to_job(
                        oferta,
                        perfil,
                        output_dir / "cv_adaptado.pdf",
                        cover_letter_pdf=output_dir / "cover_letter.pdf",
                        cover_letter_md=docs.cover_letter_md,
                    )
                    await save_application_output_async(oferta, docs, application_result)
                    estado = _estado_from_application_result(
                        application_result.enviado,
                        application_result.mensaje,
                    )
                    
                    record = RegistroPostulacion(
                        empresa=oferta.empresa,
                        cargo=oferta.titulo,
                        plataforma=oferta.plataforma,
                        url=url,
                        estado=estado,
                        carpeta_output=str(output_dir),
                        notas=f"Match: {docs.match_score:.0%} | {application_result.mensaje}",
                    )
                    add_record(record)
                    
                    if application_result.enviado:
                        aplicaciones_hoy += 1
                    urls_procesadas.add(url)
                    
                    console.print(
                        f"[bold green]  {'✓ APLICADO' if application_result.enviado else '• PREPARADO'}[/bold green] | "
                        f"{oferta.empresa} - {oferta.titulo} | "
                        f"Match: {docs.match_score:.0%} | "
                        f"{application_result.mensaje}"
                    )
                    
                    # Delay entre aplicaciones
                    if application_result.enviado and aplicaciones_hoy < prefs.max_aplicaciones_por_dia:
                        console.print(f"[dim]  Esperando {prefs.delay_entre_aplicaciones_segundos}s...[/dim]")
                        await asyncio.sleep(prefs.delay_entre_aplicaciones_segundos)
                
                except Exception as e:
                    console.print(f"[red]  ✗ Error inesperado: {e}[/red]")
                    urls_procesadas.add(url)
                    continue
            
            # Resumen de iteración
            console.print(f"\n[bold]Aplicaciones hoy: {aplicaciones_hoy}/{prefs.max_aplicaciones_por_dia}[/bold]")
            
            # Verificar si alcanzamos max_iterations
            if max_iterations and iteration >= max_iterations:
                console.print(f"\n[green]✓ Completadas {max_iterations} iteraciones.[/green]")
                break
            
            # Esperar antes de la siguiente búsqueda (5 minutos)
            console.print("[dim]Esperando 5 minutos antes de la siguiente búsqueda...[/dim]")
            await asyncio.sleep(300)
    
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⏸️  Detenido por el usuario.[/yellow]")
    
    console.print(f"\n[bold green]═══ Sesión Finalizada ═══[/bold green]")
    console.print(f"Total aplicaciones realizadas hoy: {aplicaciones_hoy}")

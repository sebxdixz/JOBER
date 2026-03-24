"""Comando jober run - modo autonomo de busqueda y aplicacion continua."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from jober.agents.auto_apply import auto_apply_to_job
from jober.agents.autonomous_search import find_new_leads, lead_to_oferta
from jober.agents.offer_evaluator import evaluate_offer, evaluate_offer_for_scout
from jober.agents.orchestrator import build_apply_graph
from jober.core.config import ensure_profile_dirs, resolve_profile_id
from jober.core.models import RegistroPostulacion, EstadoPostulacion, JobLead
from jober.core.state import new_state, view_state
from jober.utils.file_io import (
    ensure_job_output_dir,
    load_last_scout,
    load_perfil_maestro,
    save_application_output_async,
    write_output_artifact,
)
from jober.utils.runtime_status import update_status, upsert_job
from jober.utils.status_server import start_status_server, stop_status_server
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


def _load_warm_start_leads(profile_id: str, limit: int) -> list[JobLead]:
    scout_payload = load_last_scout(profile_id)
    if not scout_payload or not scout_payload.get("candidates"):
        return []

    leads: list[JobLead] = []
    seen: set[str] = set()
    for candidate in scout_payload.get("candidates", [])[: max(limit, 0)]:
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("url", "")).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        leads.append(JobLead(
            url=url,
            titulo=str(candidate.get("cargo", "")).strip(),
            empresa=str(candidate.get("empresa", "")).strip(),
            ubicacion=str(candidate.get("ubicacion", "")).strip(),
            plataforma=str(candidate.get("plataforma", "")).strip(),
            snippet=str(candidate.get("snippet", "")).strip(),
            source=str(candidate.get("source", "last_scout")).strip() or "last_scout",
        ))
    return leads


async def autonomous_run_loop(
    max_iterations: int | None = None,
    per_platform: int = 3,
    profile_id: str | None = None,
    ui: bool = True,
    ui_port: int = 8765,
    sleep_seconds: int = 120,
):
    """Loop principal de busqueda y aplicacion autonoma."""
    profile_id = resolve_profile_id(profile_id)

    # Cargar perfil
    perfil = load_perfil_maestro(profile_id)
    if perfil is None:
        console.print("[red]⚠️  No hay perfil maestro. Ejecuta 'jober init' primero.[/red]")
        return

    prefs = perfil.preferencias
    if "linkedin" in prefs.plataformas_activas:
        storage_state_path = ensure_profile_dirs(profile_id).profile_dir / "playwright_storage.json"
        if not storage_state_path.exists():
            console.print(
                "[yellow]LinkedIn requiere sesion activa. Ejecuta: jober login linkedin[/yellow]"
            )
    apply_graph = build_apply_graph()
    meetfrank_engine = os.getenv("JOBER_MEETFRANK_ENGINE", "").strip().lower()
    if meetfrank_engine == "playwright" and "meetfrank" in prefs.plataformas_activas:
        console.print("[yellow]MeetFrank usa Playwright: mas lento y puede generar costos extra.[/yellow]")
    server = None
    if ui:
        server = start_status_server(profile_id, port=ui_port)
        if server is None:
            console.print("[yellow]No se pudo iniciar la UI local (puerto ocupado).[/yellow]")
        else:
            console.print(f"[green]UI local: http://127.0.0.1:{ui_port}[/green]")
    update_status(profile_id, mode="run", stage="starting", message="Inicializando...", jobs=[])
    console.print(Panel.fit(
        f"[bold cyan]🤖 Modo Autonomo Activado[/bold cyan]\n\n"
        f"Perfil: {profile_id}\n"
        f"Roles: {', '.join(prefs.roles_deseados[:3]) or 'Cualquiera'}\n"
        f"Match minimo: {prefs.min_match_score:.0%}\n"
        f"Max aplicaciones/dia: {prefs.max_aplicaciones_por_dia}\n"
        f"Scout por plataforma: {per_platform}\n"
        f"Plataformas: {', '.join(prefs.plataformas_activas)}\n\n"
        f"[yellow]Presiona Ctrl+C para detener[/yellow]",
        border_style="cyan",
    ))

    iteration = 0
    aplicaciones_hoy = 0
    ultimo_reset_dia = datetime.now().date()
    warm_start_leads = _load_warm_start_leads(profile_id, max(3, per_platform))

    # Cargar URLs ya procesadas
    records = read_all_records(profile_id)
    urls_procesadas = {r.url for r in records if r.url}

    try:
        while True:
            iteration += 1

            # Reset contador diario
            hoy = datetime.now().date()
            if hoy != ultimo_reset_dia:
                aplicaciones_hoy = 0
                ultimo_reset_dia = hoy

            # Verificar limite diario
            if aplicaciones_hoy >= prefs.max_aplicaciones_por_dia:
                console.print(
                    f"\n[yellow]⏸️  Limite diario alcanzado ({prefs.max_aplicaciones_por_dia}). Esperando...[/yellow]"
                )
                await asyncio.sleep(3600)
                continue

            console.print(f"\n[bold cyan]═══ Iteracion {iteration} ═══[/bold cyan]")

            # 1. Buscar nuevas ofertas
            console.print("[cyan]🔍 Buscando nuevas ofertas...[/cyan]")
            update_status(profile_id, stage="searching", message="Buscando nuevas ofertas...")
            fetch_per_platform = max(per_platform * 3, 12)
            leads = await find_new_leads(
                perfil,
                max_per_platform=fetch_per_platform,
                search_round=max(iteration - 1, 0),
            )
            if warm_start_leads:
                warm_candidates = [lead for lead in warm_start_leads if lead.url and lead.url not in urls_procesadas]
                if warm_candidates:
                    leads = warm_candidates + leads
                    console.print(
                        f"[dim]  Warm start: reutilizando {len(warm_candidates)} oferta(s) del ultimo scout.[/dim]"
                    )
            leads = [lead for lead in leads if lead.url and lead.url not in urls_procesadas]
            urls_nuevas = [lead.url for lead in leads]

            if not urls_nuevas:
                console.print("[yellow]  No hay ofertas nuevas. Esperando 5 minutos...[/yellow]")
                update_status(profile_id, stage="waiting", message="Sin ofertas nuevas. Esperando...")
                await asyncio.sleep(sleep_seconds)
                continue

            console.print(f"[green]  ✓ {len(urls_nuevas)} ofertas nuevas encontradas[/green]")

            warm_start_leads = []

            # 2. Prefiltrado local rapido
            update_status(profile_id, stage="prefilter", message=f"Prefiltrando {len(leads)} ofertas...")
            evaluated = []
            filtered_reasons: dict[str, int] = {}
            for lead in leads:
                oferta_preview = lead_to_oferta(lead)
                output_dir = ensure_job_output_dir(
                    profile_id,
                    oferta_preview,
                    url=lead.url,
                    plataforma=lead.plataforma,
                    empresa=lead.empresa,
                    cargo=lead.titulo,
                )
                write_output_artifact(output_dir, "lead_snapshot.json", {
                    "timestamp": datetime.now().isoformat(),
                    "phase": "prefilter",
                    "lead": lead.model_dump(),
                    "oferta_preview": oferta_preview.model_dump(),
                })
                is_candidate, notes, quick_score = evaluate_offer_for_scout(oferta_preview, perfil)
                if is_candidate:
                    write_output_artifact(output_dir, "prefilter_result.json", {
                        "timestamp": datetime.now().isoformat(),
                        "status": "passed",
                        "score": quick_score,
                        "notes": notes,
                    })
                    evaluated.append((lead, quick_score, output_dir))
                else:
                    reason = notes[0] if notes else "Filtrada"
                    filtered_reasons[reason] = filtered_reasons.get(reason, 0) + 1
                    urls_procesadas.add(lead.url)
                    write_output_artifact(output_dir, "prefilter_result.json", {
                        "timestamp": datetime.now().isoformat(),
                        "status": "filtered",
                        "score": quick_score,
                        "notes": notes,
                    })
                    upsert_job(profile_id, {
                        "url": lead.url,
                        "title": oferta_preview.titulo,
                        "company": oferta_preview.empresa,
                        "location": oferta_preview.ubicacion,
                        "platform": oferta_preview.plataforma,
                        "status": "filtered",
                        "notes": " | ".join(notes[:2]),
                        "output_dir": str(output_dir),
                    })

            if not evaluated:
                if filtered_reasons:
                    summary = " | ".join(f"{reason}: {count}" for reason, count in filtered_reasons.items())
                    console.print(f"[dim]  Motivos de descarte: {summary}[/dim]")
                console.print("[yellow]  No hubo ofertas que pasaran el filtro rapido.[/yellow]")
                update_status(profile_id, stage="waiting", message="Filtro rapido sin resultados. Esperando...")
                await asyncio.sleep(sleep_seconds)
                continue

            evaluated.sort(key=lambda item: item[1], reverse=True)
            max_llm = min(6, max(4, per_platform))
            candidates = evaluated[:max_llm]
            for lead, _score, output_dir in evaluated[max_llm:]:
                urls_procesadas.add(lead.url)
                write_output_artifact(output_dir, "prefilter_result.json", {
                    "timestamp": datetime.now().isoformat(),
                    "status": "ranked_out",
                    "score": _score,
                    "notes": ["No entro en el top para revision profunda en esta iteracion."],
                })

            # 3. Procesar cada oferta
            for idx, (lead, _score, output_dir) in enumerate(candidates, 1):
                if aplicaciones_hoy >= prefs.max_aplicaciones_por_dia:
                    break

                url = lead.url
                console.print(f"\n[cyan]📄 [{idx}/{len(candidates)}] Analizando: {url[:80]}...[/cyan]")
                write_output_artifact(output_dir, "analysis_trace.json", {
                    "timestamp": datetime.now().isoformat(),
                    "status": "analyzing",
                    "url": url,
                    "lead": lead.model_dump(),
                })
                upsert_job(profile_id, {
                    "url": url,
                    "title": lead.titulo,
                    "company": lead.empresa,
                    "location": lead.ubicacion,
                    "platform": lead.plataforma,
                    "status": "analyzing",
                    "output_dir": str(output_dir),
                })

                try:
                    state = new_state(job_url=url, perfil=perfil)
                    result = await apply_graph.ainvoke(state)
                    result = view_state(result)

                    if result.error:
                        console.print(f"[red]  ✗ Error en pipeline: {result.error[:100]}[/red]")
                        urls_procesadas.add(url)
                        write_output_artifact(output_dir, "pipeline_error.json", {
                            "timestamp": datetime.now().isoformat(),
                            "error": result.error,
                            "screening_notes": result.screening_notes,
                        })
                        upsert_job(profile_id, {
                            "url": url,
                            "status": "error",
                            "output_dir": str(output_dir),
                        })
                        continue

                    if not result.should_apply:
                        motivo = " | ".join(result.screening_notes[:3])
                        console.print(f"[yellow]  ⊘ Filtrada por screening: {motivo}[/yellow]")
                        urls_procesadas.add(url)
                        write_output_artifact(output_dir, "screening_result.json", {
                            "timestamp": datetime.now().isoformat(),
                            "status": "filtered",
                            "phase": "screening",
                            "screening_notes": result.screening_notes,
                            "oferta": result.oferta.model_dump(),
                            "match_score": result.documentos.match_score,
                        })
                        upsert_job(profile_id, {
                            "url": url,
                            "status": "filtered",
                            "output_dir": str(output_dir),
                        })
                        continue

                    oferta = result.oferta
                    docs = result.documentos

                    # Verificar match minimo
                    if docs.match_score < prefs.min_match_score:
                        console.print(
                            f"[yellow]  ⊘ Match bajo ({docs.match_score:.0%} < {prefs.min_match_score:.0%})[/yellow]"
                        )
                        urls_procesadas.add(url)
                        write_output_artifact(output_dir, "screening_result.json", {
                            "timestamp": datetime.now().isoformat(),
                            "status": "low_match",
                            "phase": "match_gate",
                            "screening_notes": result.screening_notes,
                            "oferta": oferta.model_dump(),
                            "match_score": docs.match_score,
                            "min_match_required": prefs.min_match_score,
                        })
                        upsert_job(profile_id, {
                            "url": url,
                            "status": "low_match",
                            "output_dir": str(output_dir),
                        })
                        continue

                    # Guardar aplicacion (Markdown + PDF)
                    output_dir = await save_application_output_async(
                        oferta,
                        docs,
                        profile_id=profile_id,
                        output_dir=output_dir,
                    )
                    application_result = await auto_apply_to_job(
                        oferta,
                        perfil,
                        output_dir / "cv_adaptado.pdf",
                        cover_letter_pdf=output_dir / "cover_letter.pdf",
                        cover_letter_md=docs.cover_letter_md,
                    )
                    await save_application_output_async(
                        oferta,
                        docs,
                        application_result,
                        profile_id=profile_id,
                        output_dir=output_dir,
                    )
                    write_output_artifact(output_dir, "run_trace.json", {
                        "timestamp": datetime.now().isoformat(),
                        "status": "applied" if application_result.enviado else "prepared",
                        "screening_notes": result.screening_notes,
                        "match_score": docs.match_score,
                        "oferta": oferta.model_dump(),
                        "application_result": application_result.model_dump(),
                    })
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
                    add_record(record, profile_id)

                    if application_result.enviado:
                        aplicaciones_hoy += 1
                    urls_procesadas.add(url)

                    upsert_job(profile_id, {
                        "url": url,
                        "title": oferta.titulo,
                        "company": oferta.empresa,
                        "location": oferta.ubicacion,
                        "platform": oferta.plataforma,
                        "status": "applied" if application_result.enviado else "prepared",
                        "output_dir": str(output_dir),
                    })

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

                except Exception as exc:
                    console.print(f"[red]  ✗ Error inesperado: {exc}[/red]")
                    urls_procesadas.add(url)
                    write_output_artifact(output_dir, "pipeline_error.json", {
                        "timestamp": datetime.now().isoformat(),
                        "error": str(exc),
                    })
                    upsert_job(profile_id, {
                        "url": url,
                        "status": "error",
                        "output_dir": str(output_dir),
                    })
                    continue

            # Resumen de iteracion
            console.print(f"\n[bold]Aplicaciones hoy: {aplicaciones_hoy}/{prefs.max_aplicaciones_por_dia}[/bold]")

            # Verificar si alcanzamos max_iterations
            if max_iterations and iteration >= max_iterations:
                console.print(f"\n[green]✓ Completadas {max_iterations} iteraciones.[/green]")
                break

            # Esperar antes de la siguiente busqueda (5 minutos)
            console.print(f"[dim]Esperando {sleep_seconds}s antes de la siguiente busqueda...[/dim]")
            update_status(profile_id, stage="waiting", message=f"Esperando {sleep_seconds}s...")
            await asyncio.sleep(sleep_seconds)

    except KeyboardInterrupt:
        console.print("\n\n[yellow]⏸️  Detenido por el usuario.[/yellow]")
    finally:
        update_status(profile_id, stage="done", message="Sesion finalizada")
        stop_status_server(server)

    console.print(f"\n[bold green]═══ Sesion Finalizada ═══[/bold green]")
    console.print(f"Total aplicaciones realizadas hoy: {aplicaciones_hoy}")

"""Helper para el flujo de onboarding de preferencias laborales.

Ejecuta una entrevista conversacional profunda que cubre:
cargo, experiencia, habilidades, condiciones, salario, deal breakers, etc.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from jober.agents.onboarding_preferences import onboarding_preferences_node, extract_preferences_node
from jober.core.models import PerfilMaestro


console = Console()


async def run_preferences_flow(perfil: PerfilMaestro) -> dict:
    """Ejecuta el flujo conversacional completo de onboarding de preferencias."""
    
    # Estado como dict para pasar entre nodos
    state = {
        "messages": [],
        "perfil": perfil,
        "next_step": "wait_user_input",
    }
    
    # Primera pregunta del agente
    result = await onboarding_preferences_node(state)
    
    if result.get("error"):
        return result
    
    question_count = 0
    
    # Loop conversacional
    while result.get("next_step") == "wait_user_input":
        # Mostrar la pregunta del agente
        messages = result.get("messages", [])
        last_msg = messages[-1] if messages else None
        
        if last_msg and isinstance(last_msg, AIMessage):
            question_count += 1
            console.print(f"\n[bold cyan]Jober:[/bold cyan] {last_msg.content}")
        
        # Input del usuario
        user_input = Prompt.ask("\n[yellow]Tu[/yellow]")
        
        if user_input.lower() in ("skip", "saltar", "fin", "listo"):
            console.print("\n[dim]Extrayendo tus preferencias de la conversacion...[/dim]")
            result["next_step"] = "extract_preferences"
            break
        
        # Agregar respuesta del usuario al historial y continuar
        result["messages"] = messages + [HumanMessage(content=user_input)]
        result["perfil"] = perfil
        result = await onboarding_preferences_node(result)
        
        if result.get("error"):
            return result
    
    # Extraer preferencias estructuradas de toda la conversacion
    if result.get("next_step") == "extract_preferences":
        console.print("\n[cyan]Procesando tus respuestas...[/cyan]")
        result["perfil"] = perfil
        extract_result = await extract_preferences_node(result)
        
        if extract_result.get("error"):
            return extract_result
        
        # Mostrar resumen de preferencias extraidas
        prefs = extract_result.get("preferencias")
        if prefs:
            console.print(Panel.fit(
                f"[bold green]Preferencias configuradas[/bold green]\n\n"
                f"[cyan]Roles:[/cyan] {', '.join(prefs.roles_deseados[:5]) or 'No especificado'}\n"
                f"[cyan]Nivel:[/cyan] {prefs.nivel_experiencia or 'No especificado'} ({prefs.anos_experiencia} anios exp.)\n"
                f"[cyan]Habilidades dominadas:[/cyan] {', '.join(prefs.habilidades_dominadas[:5]) or '-'}\n"
                f"[cyan]Aprendiendo:[/cyan] {', '.join(prefs.habilidades_en_aprendizaje[:3]) or '-'}\n"
                f"[cyan]Modalidad:[/cyan] {', '.join(prefs.modalidad)}\n"
                f"[cyan]Jornada:[/cyan] {prefs.jornada}\n"
                f"[cyan]Salario:[/cyan] {prefs.salario_minimo or '-'} - {prefs.salario_ideal or '-'}\n"
                f"[cyan]Match minimo:[/cyan] {prefs.min_match_score:.0%}\n"
                f"[cyan]Deal breakers:[/cyan] {', '.join(prefs.deal_breakers[:3]) or 'Ninguno'}\n"
                f"[cyan]Motivacion:[/cyan] {prefs.motivacion[:100] or '-'}\n"
                f"\n[dim]Preguntas respondidas: {question_count}[/dim]",
                border_style="green",
            ))
        
        return extract_result
    
    return result

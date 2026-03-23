"""Helper para el flujo de onboarding de preferencias laborales."""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.prompt import Prompt

from jober.agents.onboarding_preferences import onboarding_preferences_node, extract_preferences_node
from jober.core.models import PerfilMaestro
from jober.core.state import JoberState


console = Console()


async def run_preferences_flow(perfil: PerfilMaestro) -> dict:
    """Ejecuta el flujo conversacional de configuración de preferencias."""
    state = JoberState(perfil=perfil)
    
    # Primera pregunta
    result = await onboarding_preferences_node(state)
    
    # Loop conversacional
    while result.get("next_step") == "wait_user_input":
        last_msg = result.get("messages", [])[-1] if result.get("messages") else None
        if last_msg:
            console.print(f"\n[bold cyan]🤖 Jober:[/bold cyan] {last_msg.content}")
        
        user_input = Prompt.ask("[yellow]Tú[/yellow]")
        
        if user_input.lower() in ("skip", "saltar", "fin"):
            result["next_step"] = "extract_preferences"
            break
        
        result["messages"] = result.get("messages", []) + [HumanMessage(content=user_input)]
        result = await onboarding_preferences_node(result)
    
    # Extraer preferencias de la conversación
    if result.get("next_step") == "extract_preferences":
        extract_result = await extract_preferences_node(result)
        return extract_result
    
    return result

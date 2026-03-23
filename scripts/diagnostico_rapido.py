"""Diagnóstico rápido de por qué no encuentra ofertas relevantes."""

import asyncio
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jober.agents.autonomous_search import find_new_opportunities, is_relevant_offer
from jober.agents.job_scraper import job_scraper_node
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro


console = Console()


async def main():
    console.print(Panel.fit("[bold red]Diagnóstico Rápido[/bold red]", border_style="red"))
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        console.print("❌ No hay perfil")
        return
    
    # Configurar preferencias AI/ML
    perfil.preferencias = PreferenciasLaborales(
        roles_deseados=["AI Engineer", "ML Engineer", "Machine Learning Engineer"],
        modalidad=["remoto", "remote", "Remote", "Remoto"],
        habilidades_must_have=["Python", "Machine Learning"],
        min_match_score=0.5
    )
    
    console.print(f"\n📋 Perfil: {perfil.nombre}")
    console.print(f"🎯 Roles: {', '.join(perfil.preferencias.roles_deseados)}")
    console.print(f"🏠 Modalidad: {', '.join(perfil.preferencias.modalidad)}")
    console.print(f"💻 Habilidades: {', '.join(perfil.preferencias.habilidades_must_have)}")
    
    # Buscar ofertas
    console.print("\n🔍 Buscando ofertas...")
    urls = await find_new_opportunities(perfil, max_per_platform=3)
    console.print(f"   URLs encontradas: {len(urls)}")
    
    if not urls:
        console.print("❌ No se encontraron URLs")
        return
    
    # Analizar primeras 3 ofertas
    table = Table(title="Análisis de Ofertas")
    table.add_column("Título", style="cyan")
    table.add_column("Empresa", style="green")
    table.add_column("Modalidad", style="yellow")
    table.add_column("¿Python?", style="red")
    table.add_column("¿Relevante?", style="bold")
    
    for i, url in enumerate(urls[:3]):
        console.print(f"\n--- Oferta {i+1} ---")
        console.print(f"URL: {url}")
        
        try:
            # Scrapear
            state = JoberState(job_url=url, perfil=perfil)
            result = await job_scraper_node(state)
            
            if result.get("error"):
                console.print(f"❌ Error scrapeando: {result['error']}")
                continue
            
            oferta = result["oferta"]
            console.print(f"Título: {oferta.titulo}")
            console.print(f"Empresa: {oferta.empresa}")
            console.print(f"Modalidad: {oferta.modalidad}")
            console.print(f"Ubicación: {oferta.ubicacion}")
            
            # Verificar filtros manualmente
            modalidad_ok = not oferta.modalidad or any(m.lower() in oferta.modalidad.lower() for m in perfil.preferencias.modalidad)
            console.print(f"✅ Modalidad OK: {modalidad_ok}")
            
            rol_ok = any(role.lower() in oferta.titulo.lower() for role in perfil.preferencias.roles_deseados)
            console.print(f"✅ Rol OK: {rol_ok}")
            
            texto_completo = (oferta.descripcion + " " + " ".join(oferta.requisitos)).lower()
            python_ok = "python" in texto_completo
            console.print(f"✅ Python OK: {python_ok}")
            
            relevante = is_relevant_offer(oferta, perfil)
            console.print(f"🎯 RELEVANTE: {relevante}")
            
            # Agregar a tabla
            table.add_row(
                oferta.titulo[:40],
                oferta.empresa,
                oferta.modalidad or "-",
                "✅" if python_ok else "❌",
                "✅" if relevante else "❌"
            )
            
            # Mostrar requisitos si no es relevante
            if not relevante:
                console.print("\n📋 Requisitos:")
                for req in oferta.requisitos[:5]:
                    console.print(f"   • {req}")
            
        except Exception as e:
            console.print(f"❌ Excepción: {str(e)[:100]}")
    
    console.print("\n")
    console.print(table)


if __name__ == "__main__":
    asyncio.run(main())

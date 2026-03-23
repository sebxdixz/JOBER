"""Diagnóstico simple sin emojis."""

import asyncio
from jober.agents.autonomous_search import find_new_opportunities, is_relevant_offer
from jober.agents.job_scraper import job_scraper_node
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro


async def main():
    print("=" * 60)
    print("DIAGNOSTICO RAPIDO - POR QUÉ NO HAY OFERTAS RELEVANTES")
    print("=" * 60)
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        print("ERROR: No hay perfil")
        return
    
    # Configurar preferencias AI/ML
    perfil.preferencias = PreferenciasLaborales(
        roles_deseados=["AI Engineer", "ML Engineer", "Machine Learning Engineer", "Data Scientist"],
        modalidad=["remoto", "remote", "Remote", "Remoto", "hibrido", "hybrid"],
        habilidades_must_have=["Python", "Machine Learning", "ML"],
        min_match_score=0.5
    )
    
    print(f"\nPerfil: {perfil.nombre}")
    print(f"Roles buscados: {', '.join(perfil.preferencias.roles_deseados)}")
    print(f"Modalidad: {', '.join(perfil.preferencias.modalidad)}")
    print(f"Habilidades requeridas: {', '.join(perfil.preferencias.habilidades_must_have)}")
    
    # Buscar ofertas
    print("\nBuscando ofertas...")
    urls = await find_new_opportunities(perfil, max_per_platform=3)
    print(f"URLs encontradas: {len(urls)}")
    
    if not urls:
        print("ERROR: No se encontraron URLs")
        return
    
    # Analizar ofertas
    print("\n" + "=" * 60)
    print("ANALISIS DE OFERTAS")
    print("=" * 60)
    
    relevantes = 0
    
    for i, url in enumerate(urls[:5]):
        print(f"\n--- Oferta {i+1} ---")
        print(f"URL: {url[:80]}...")
        
        try:
            # Scrapear
            state = JoberState(job_url=url, perfil=perfil)
            result = await job_scraper_node(state)
            
            if result.get("error"):
                print(f"ERROR scrapeando: {result['error']}")
                continue
            
            oferta = result["oferta"]
            print(f"Titulo: {oferta.titulo}")
            print(f"Empresa: {oferta.empresa}")
            print(f"Modalidad: {oferta.modalidad or 'NO ESPECIFICADA'}")
            print(f"Ubicacion: {oferta.ubicacion or 'NO ESPECIFICADA'}")
            
            # Verificar filtros
            print("\nVerificacion de filtros:")
            
            # 1. Modalidad
            modalidad_ok = True
            if oferta.modalidad:
                modalidad_ok = any(m.lower() in oferta.modalidad.lower() for m in perfil.preferencias.modalidad)
            print(f"  1. Modalidad OK: {modalidad_ok}")
            if not modalidad_ok:
                print(f"     -> Modalidad de oferta: '{oferta.modalidad}'")
                print(f"     -> Modalidades aceptadas: {perfil.preferencias.modalidad}")
            
            # 2. Rol
            rol_ok = any(role.lower() in oferta.titulo.lower() for role in perfil.preferencias.roles_deseados)
            print(f"  2. Rol OK: {rol_ok}")
            if not rol_ok:
                print(f"     -> Titulo: '{oferta.titulo}'")
                print(f"     -> Roles buscados: {perfil.preferencias.roles_deseados}")
            
            # 3. Habilidades
            texto_completo = (oferta.descripcion + " " + " ".join(oferta.requisitos)).lower()
            habilidades_ok = any(skill.lower() in texto_completo for skill in perfil.preferencias.habilidades_must_have)
            print(f"  3. Habilidades OK: {habilidades_ok}")
            if not habilidades_ok:
                print(f"     -> Habilidades en descripcion/requisitos:")
                for skill in perfil.preferencias.habilidades_must_have:
                    presente = skill.lower() in texto_completo
                    print(f"        - {skill}: {'SI' if presente else 'NO'}")
            
            # Resultado final
            relevante = is_relevant_offer(oferta, perfil)
            print(f"\n  RESULTADO: {'RELEVANTE' if relevante else 'NO RELEVANTE'}")
            
            if relevante:
                relevantes += 1
            
            # Mostrar primeros requisitos si no es relevante
            if not relevante and oferta.requisitos:
                print(f"\n  Requisitos (primeros 5):")
                for req in oferta.requisitos[:5]:
                    print(f"    - {req}")
            
        except Exception as e:
            print(f"ERROR: {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    print(f"RESUMEN: {relevantes} ofertas relevantes de {len(urls[:5])} analizadas")
    print("=" * 60)
    
    if relevantes == 0:
        print("\nPOSIBLES PROBLEMAS IDENTIFICADOS:")
        print("1. Los roles 'AI Engineer' pueden no ser comunes en las ofertas")
        print("2. La modalidad 'remoto' puede estar escrita como 'Remote', 'Home Office', etc.")
        print("3. Las ofertas pueden no mencionar explicitamente 'Machine Learning'")
        print("\nSUGERENCIAS:")
        print("- Ampliar roles buscados: 'Data Scientist', 'Python Developer'")
        print("- Ser mas flexible con modalidad")
        print("- Bajar el umbral de habilidades requeridas")


if __name__ == "__main__":
    asyncio.run(main())

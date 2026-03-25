"""Test completo del flujo de aplicación en LinkedIn con perfil real."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo, PerfilMaestro
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import auto_apply_to_job
from jober.core.logging import logger


async def test_full_apply():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 80)
    print("TEST COMPLETO: APLICACION EN LINKEDIN CON PERFIL REAL")
    print("=" * 80)
    print(f"\nURL: {url}")
    
    # Cargar perfil real
    print("\n[1/4] Cargando perfil maestro...")
    try:
        perfil = load_perfil_maestro()
        if not perfil:
            print(f"  ✗ No se encontró perfil maestro")
            return
        print(f"  ✓ Perfil cargado: {perfil.nombre}")
        print(f"  Email: {perfil.email}")
        print(f"  Roles deseados: {', '.join(perfil.preferencias.roles_deseados[:3])}...")
    except Exception as e:
        print(f"  ✗ Error cargando perfil: {e}")
        return
    
    # Crear oferta simulada
    print("\n[2/4] Creando oferta de trabajo...")
    oferta = OfertaTrabajo(
        titulo="Junior AI/ML Engineer (Remote)",
        empresa="ChatGPT Jobs",
        url=url,
        plataforma="linkedin",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="AI/ML Engineer position for building LLM applications",
        requisitos=["Python", "Machine Learning", "LLMs"],
        salario="",
        fecha_publicacion="2024-03-24"
    )
    print(f"  ✓ Oferta creada: {oferta.titulo} @ {oferta.empresa}")
    
    # Generar CV y cover letter (simulados para test)
    print("\n[3/4] Preparando documentos...")
    
    # Crear directorio temporal para documentos
    temp_dir = Path("temp_test_docs")
    temp_dir.mkdir(exist_ok=True)
    
    cv_path = temp_dir / "cv_test.pdf"
    cover_letter_path = temp_dir / "cover_letter_test.pdf"
    
    # Crear PDFs dummy (solo para test)
    cv_path.write_text("CV Test Content")
    cover_letter_path.write_text("Cover Letter Test Content")
    
    cover_letter_text = f"""Estimado equipo de {oferta.empresa},

Me dirijo a ustedes para expresar mi interés en la posición de {oferta.titulo}.

Con experiencia en LangGraph, Pydantic, y orquestación de LLMs, he desarrollado sistemas multi-agente 
en producción que automatizan procesos complejos. Mi trabajo en Grupo Axo incluyó:

- Arquitectura de pipelines autónomos con LangGraph y PostgreSQL
- Reducción de alucinación en OCR a <1% usando Pydantic
- Despliegue de infraestructura contenizada con Docker y Kubernetes

Estoy especialmente interesado en roles remotos de AI/ML Engineering donde pueda aplicar mi experiencia
en automatización y sistemas de IA productivos.

Adjunto mi CV para su consideración.

Saludos cordiales,
{perfil.nombre}"""
    
    print(f"  ✓ CV: {cv_path}")
    print(f"  ✓ Cover Letter: {cover_letter_path}")
    
    # Ejecutar aplicación
    print("\n[4/4] Ejecutando flujo de aplicación...")
    print("-" * 80)
    
    try:
        resultado = await auto_apply_to_job(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_path,
            cover_letter_pdf=cover_letter_path,
            cover_letter_md=cover_letter_text
        )
        
        print("\n" + "=" * 80)
        print("RESULTADO DE LA APLICACION")
        print("=" * 80)
        
        print(f"\nEnviado: {resultado.enviado}")
        print(f"Método: {resultado.metodo}")
        print(f"Plataforma: {resultado.plataforma}")
        print(f"URL final: {resultado.url_final}")
        print(f"Mensaje: {resultado.mensaje}")
        
        if resultado.detalles:
            print(f"\nDetalles:")
            for key, value in resultado.detalles.items():
                print(f"  {key}: {value}")
        
        if resultado.enviado:
            print("\n✓✓✓ APLICACION EXITOSA ✓✓✓")
        else:
            print("\n✗✗✗ APLICACION FALLIDA ✗✗✗")
            print(f"\nRazón: {resultado.mensaje}")
        
    except Exception as e:
        print(f"\n✗ Error durante la aplicación: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpiar archivos temporales
        try:
            cv_path.unlink()
            cover_letter_path.unlink()
            temp_dir.rmdir()
        except:
            pass
    
    print("\n" + "=" * 80)
    print("TEST COMPLETADO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_full_apply())

"""Test con cualquier oferta de LinkedIn que proporciones."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import auto_apply_to_job


async def test_any_job(url: str):
    print("=" * 80)
    print("TEST: APLICACION AUTOMATICA EN LINKEDIN")
    print("=" * 80)
    print(f"\nURL: {url}")
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        print("✗ No se encontró perfil maestro")
        return
    
    print(f"\n✓ Perfil: {perfil.nombre}")
    
    # Crear oferta
    oferta = OfertaTrabajo(
        titulo="Job from LinkedIn",
        empresa="Company",
        url=url,
        plataforma="linkedin",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="Job description",
        requisitos=[],
        salario="",
        fecha_publicacion="2024-03-24"
    )
    
    # Preparar documentos
    temp_dir = Path("temp_test_docs")
    temp_dir.mkdir(exist_ok=True)
    cv_path = temp_dir / "cv_test.pdf"
    cover_letter_path = temp_dir / "cover_letter_test.pdf"
    
    cv_path.write_text("CV Test Content")
    cover_letter_path.write_text("Cover Letter Test Content")
    
    cover_letter_md = f"""Estimado equipo,

Me interesa la posición. Tengo experiencia en LangGraph, Pydantic, y LLMs.

Saludos,
{perfil.nombre}"""
    
    print("\n" + "=" * 80)
    print("EJECUTANDO APLICACION AUTOMATICA")
    print("=" * 80)
    print("\nEl navegador se abrirá y el agente intentará:")
    print("1. Encontrar el botón de aplicación (cualquier tipo)")
    print("2. Hacer clic en él")
    print("3. Detectar qué tipo de aplicación es (Easy Apply, normal, externa)")
    print("4. Rellenar el formulario automáticamente")
    print("5. Enviar la aplicación")
    print("\nObserva el navegador para ver qué hace el agente...")
    print("=" * 80)
    
    try:
        resultado = await auto_apply_to_job(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_path,
            cover_letter_pdf=cover_letter_path,
            cover_letter_md=cover_letter_md
        )
        
        print("\n" + "=" * 80)
        print("RESULTADO")
        print("=" * 80)
        
        print(f"\n{'✓' if resultado.enviado else '✗'} Enviado: {resultado.enviado}")
        print(f"  Método: {resultado.metodo}")
        print(f"  Mensaje: {resultado.mensaje}")
        
        if resultado.detalles:
            print(f"\n  Detalles del proceso:")
            for key, value in resultado.detalles.items():
                if key.startswith("trace_"):
                    print(f"    {value}")
        
        if resultado.enviado:
            print("\n" + "=" * 80)
            print("✓✓✓ APLICACION EXITOSA ✓✓✓")
            print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print("✗✗✗ APLICACION FALLIDA ✗✗✗")
            print("=" * 80)
            print(f"\nRazón: {resultado.mensaje}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpiar
        try:
            cv_path.unlink()
            cover_letter_path.unlink()
            temp_dir.rmdir()
        except:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("=" * 80)
        print("USO: python scripts\\test_any_linkedin_job.py <URL>")
        print("=" * 80)
        print("\nEjemplo:")
        print('  python scripts\\test_any_linkedin_job.py "https://www.linkedin.com/jobs/view/123456789"')
        print("\nPara encontrar una oferta activa:")
        print("1. Ve a https://www.linkedin.com/jobs/")
        print("2. Busca 'AI Engineer' o 'ML Engineer'")
        print("3. Abre una oferta que tenga botón de aplicación visible")
        print("4. Copia la URL completa")
        print("5. Ejecuta este script con esa URL")
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(test_any_job(url))

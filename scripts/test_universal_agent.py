"""Test del Agente Universal con browser-use para ATS desconocidos."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import auto_apply_to_job


async def test_universal_agent(url: str):
    print("=" * 80)
    print("TEST: AGENTE UNIVERSAL CON BROWSER-USE")
    print("=" * 80)
    print(f"\nURL: {url}")
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        print("✗ No se encontró perfil maestro")
        return
    
    print(f"\n✓ Perfil: {perfil.nombre}")
    print(f"✓ Email: {perfil.email}")
    
    # Crear oferta
    oferta = OfertaTrabajo(
        titulo="Test Job Application",
        empresa="Test Company",
        url=url,
        plataforma="unknown",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="Test job description",
        requisitos=["Python", "AI"],
        salario="",
        fecha_publicacion="2024-03-25"
    )
    
    # Preparar documentos
    temp_dir = Path("temp_test_docs")
    temp_dir.mkdir(exist_ok=True)
    cv_path = temp_dir / "cv_test.pdf"
    cover_letter_path = temp_dir / "cover_letter_test.pdf"
    
    # Crear PDFs de prueba con contenido real
    cv_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/Resources <<\n/Font <<\n/F1 4 0 R\n>>\n>>\n/MediaBox [0 0 612 792]\n/Contents 5 0 R\n>>\nendobj\n4 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n5 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test CV) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000262 00000 n\n0000000341 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n433\n%%EOF")
    cover_letter_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/Resources <<\n/Font <<\n/F1 4 0 R\n>>\n>>\n/MediaBox [0 0 612 792]\n/Contents 5 0 R\n>>\nendobj\n4 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n5 0 obj\n<<\n/Length 55\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test Cover Letter) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000262 00000 n\n0000000341 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n444\n%%EOF")
    
    cover_letter_md = f"""Estimado equipo de {oferta.empresa},

Me dirijo a ustedes para expresar mi interés en la posición de {oferta.titulo}.

Con experiencia en desarrollo de sistemas multi-agente y LLMs, he trabajado en proyectos de automatización 
y orquestación de agentes autónomos. Mi experiencia incluye LangGraph, Pydantic, y deployment en producción.

Saludos cordiales,
{perfil.nombre}"""
    
    print("\n" + "=" * 80)
    print("EJECUTANDO AGENTE UNIVERSAL")
    print("=" * 80)
    print("\nEl agente universal con browser-use:")
    print("1. Usará visión para entender la página")
    print("2. Navegará el formulario dinámicamente")
    print("3. Rellenará campos con la información del perfil")
    print("4. Subirá el CV automáticamente")
    print("5. Enviará la aplicación")
    print("\nObserva el navegador para ver el agente en acción...")
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
        print(f"  Plataforma: {resultado.plataforma}")
        print(f"  Mensaje: {resultado.mensaje}")
        
        if resultado.detalles:
            print(f"\n  Trace del proceso:")
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
        print("USO: python scripts\\test_universal_agent.py <URL>")
        print("=" * 80)
        print("\nEjemplo:")
        print('  python scripts\\test_universal_agent.py "https://example.com/jobs/apply"')
        print("\nEste script probará el Agente Universal con browser-use")
        print("que puede manejar CUALQUIER formulario de aplicación.")
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(test_universal_agent(url))

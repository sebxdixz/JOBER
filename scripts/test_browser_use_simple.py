"""Test simple del agente universal con browser-use."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import _apply_universal_agent, _new_result


async def test_browser_use():
    print("=" * 80)
    print("TEST SIMPLE: BROWSER-USE AGENT")
    print("=" * 80)
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        print("✗ No se encontró perfil maestro")
        return
    
    print(f"\n✓ Perfil: {perfil.nombre}")
    print(f"✓ Email: {perfil.email}")
    
    # Crear oferta de prueba
    oferta = OfertaTrabajo(
        titulo="Software Engineer",
        empresa="Example Company",
        url="https://example.com/careers/apply",
        plataforma="unknown",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="Test job",
        requisitos=["Python"],
        salario="",
        fecha_publicacion="2024-03-25"
    )
    
    # Crear CV de prueba
    temp_dir = Path("temp_test")
    temp_dir.mkdir(exist_ok=True)
    cv_path = temp_dir / "cv.pdf"
    
    # PDF mínimo válido
    cv_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj "
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj "
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj "
        b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n"
        b"0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n164\n%%EOF"
    )
    
    print(f"\n✓ CV creado: {cv_path}")
    
    # Función de trace
    traces = []
    def trace(msg):
        traces.append(msg)
        print(f"[trace] {msg}")
    
    print("\n" + "=" * 80)
    print("EJECUTANDO AGENTE UNIVERSAL")
    print("=" * 80)
    print("\nEl agente browser-use intentará:")
    print("1. Navegar a la URL")
    print("2. Usar visión para entender la página")
    print("3. Rellenar formulario con datos del perfil")
    print("4. Subir CV")
    print("5. Enviar aplicación")
    print("\n⚠️  NOTA: example.com no tiene formulario real, esto es solo una prueba")
    print("    El agente debería navegar y reportar que no encontró formulario.")
    print("=" * 80)
    
    input("\nPresiona ENTER para iniciar el agente...")
    
    try:
        resultado = await _apply_universal_agent(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_path,
            cover_letter_pdf=None,
            cover_letter_md="Test cover letter",
            trace=trace
        )
        
        print("\n" + "=" * 80)
        print("RESULTADO")
        print("=" * 80)
        
        print(f"\n{'✓' if resultado.enviado else '✗'} Enviado: {resultado.enviado}")
        print(f"  Plataforma: {resultado.plataforma}")
        print(f"  Mensaje: {resultado.mensaje}")
        
        print("\n  Traces:")
        for t in traces:
            print(f"    - {t}")
        
        if resultado.enviado:
            print("\n✓ El agente completó exitosamente")
        else:
            print("\n✗ El agente no pudo completar (esperado para example.com)")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpiar
        try:
            cv_path.unlink()
            temp_dir.rmdir()
        except:
            pass
    
    print("\n" + "=" * 80)
    print("TEST COMPLETADO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_browser_use())

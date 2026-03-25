"""Test automático del agente universal con browser-use."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import auto_apply_to_job


async def test_browser_use_auto():
    print("=" * 80)
    print("TEST AUTOMÁTICO: AGENTE UNIVERSAL CON BROWSER-USE")
    print("=" * 80)
    
    # Usar una URL de un ATS desconocido (no Greenhouse, Lever, LinkedIn)
    # Por ejemplo, una empresa que usa su propio sistema
    test_url = "https://jobs.ashbyhq.com/example"  # Ashby es un ATS moderno
    
    print(f"\nURL de prueba: {test_url}")
    print("(Esta URL usará el agente universal porque Ashby no está en la lista de ATS conocidos)")
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        print("✗ No se encontró perfil maestro")
        return
    
    print(f"\n✓ Perfil: {perfil.nombre}")
    print(f"✓ Email: {perfil.email}")
    
    # Crear oferta
    oferta = OfertaTrabajo(
        titulo="Test Position",
        empresa="Test Company",
        url=test_url,
        plataforma="unknown",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="Test description",
        requisitos=["Python", "AI"],
        salario="",
        fecha_publicacion="2024-03-25"
    )
    
    # Crear CV de prueba
    temp_dir = Path("temp_test_auto")
    temp_dir.mkdir(exist_ok=True)
    cv_path = temp_dir / "cv_test.pdf"
    
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
    
    print(f"✓ CV creado: {cv_path}")
    
    cover_letter = """Estimado equipo,

Me dirijo a ustedes para expresar mi interés en esta posición.

Con experiencia en desarrollo de sistemas multi-agente y automatización,
creo que puedo aportar valor a su equipo.

Saludos cordiales,
Sebastián Díaz"""
    
    print("\n" + "=" * 80)
    print("INICIANDO AGENTE UNIVERSAL")
    print("=" * 80)
    print("\nEl sistema detectará que el ATS es desconocido y activará")
    print("el agente universal con browser-use automáticamente.")
    print("\nObserva el navegador que se abrirá...")
    print("=" * 80)
    
    try:
        resultado = await auto_apply_to_job(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_path,
            cover_letter_pdf=None,
            cover_letter_md=cover_letter
        )
        
        print("\n" + "=" * 80)
        print("RESULTADO DEL AGENTE UNIVERSAL")
        print("=" * 80)
        
        print(f"\n{'✓' if resultado.enviado else '✗'} Enviado: {resultado.enviado}")
        print(f"  Método: {resultado.metodo}")
        print(f"  Plataforma: {resultado.plataforma}")
        print(f"  Mensaje: {resultado.mensaje}")
        
        if resultado.detalles:
            print(f"\n  Detalles del proceso:")
            for key, value in sorted(resultado.detalles.items()):
                if key.startswith("trace_"):
                    print(f"    {value}")
        
        print("\n" + "=" * 80)
        if resultado.enviado:
            print("✓✓✓ AGENTE UNIVERSAL COMPLETÓ EXITOSAMENTE ✓✓✓")
        else:
            print("ℹ️  AGENTE UNIVERSAL EJECUTADO (puede requerir formulario real)")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ Error durante ejecución: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpiar
        try:
            cv_path.unlink()
            temp_dir.rmdir()
        except:
            pass
    
    print("\n✓ Test completado")


if __name__ == "__main__":
    print("\nINICIANDO TEST EN 3 SEGUNDOS...")
    print("(El navegador se abrirá automáticamente)\n")
    
    import time
    time.sleep(3)
    
    asyncio.run(test_browser_use_auto())

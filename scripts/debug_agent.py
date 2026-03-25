"""Debug del agente universal."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import _apply_universal_agent


async def debug():
    print("Cargando perfil...")
    perfil = load_perfil_maestro()
    
    print(f"Perfil: {perfil.nombre}")
    print(f"Experiencias: {len(perfil.experiencias) if perfil.experiencias else 0}")
    print(f"Educacion: {len(perfil.educacion) if perfil.educacion else 0}")
    
    oferta = OfertaTrabajo(
        titulo="Test",
        empresa="Test",
        url="https://example.com",
        plataforma="unknown",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="Test",
        requisitos=[],
        salario="",
        fecha_publicacion="2024-03-25"
    )
    
    cv = Path("temp_debug/cv.pdf")
    cv.parent.mkdir(exist_ok=True)
    cv.write_bytes(b"%PDF-1.4\ntest")
    
    print("\nEjecutando agente universal...")
    
    try:
        result = await _apply_universal_agent(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv,
            cover_letter_pdf=None,
            cover_letter_md="Test",
            trace=lambda x: print(f"[TRACE] {x}")
        )
        
        print(f"\nResultado: {result.enviado}")
        print(f"Mensaje: {result.mensaje}")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        cv.unlink()
        cv.parent.rmdir()


if __name__ == "__main__":
    asyncio.run(debug())

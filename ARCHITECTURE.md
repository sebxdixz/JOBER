# 🏗️ Arquitectura del Sistema

## Componentes Principales

1. **CLI Interface (Capa de Interacción):** - Construida con `Typer` o `Click`.
   - Captura el input del usuario (ej. URL del trabajo, comandos de revisión).

2. **Scraper Engine (Capa de Extracción):**
   - Módulos específicos por plataforma:
     - `linkedin_scraper.py`
     - `getonbrd_scraper.py`
     - `meetfrank_scraper.py`
   - Extrae: Título, Empresa, Descripción del cargo, Requisitos, Preguntas de postulación.

3. **LangGraph Agent (Capa de Inteligencia):**
   - **State:** Un diccionario/Pydantic model que guarda el contexto actual (datos del usuario, datos del trabajo, documentos generados).
   - **Nodos:**
     - `analizar_oferta`: Extrae keywords y requerimientos.
     - `adaptar_cv`: Modifica el CV base (Markdown/LaTeX a PDF) resaltando la experiencia relevante.
     - `redactar_carta`: Genera un cover letter persuasivo.
     - `responder_preguntas`: Genera respuestas a las preguntas de filtrado basándose en el perfil del usuario.
   - **Edges:** Define el flujo secuencial y las validaciones (ej. ¿Falta información? -> Pedir al usuario por CLI).

4. **File Manager (Capa de Persistencia):**
   - Modifica el archivo maestro CSV (pandas o módulo `csv` nativo).
   - Crea los directorios usando `pathlib`.
   - Guarda los artefactos generados.

## Flujo de Ejecución (Happy Path)
1. CLI recibe URL -> 2. Scraper obtiene datos -> 3. LangGraph inicia el estado -> 4. LLM adapta CV y redacta carta -> 5. LLM responde preguntas -> 6. File Manager guarda todo en `/data/postulaciones/X` -> 7. File Manager actualiza el `CSV` -> 8. CLI informa éxito.
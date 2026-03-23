# 🗺️ Hoja de Ruta (Roadmap)

## Fase 1: Fundamentos y CLI (Setup Local)
- [ ] Definir el CV y perfil base en un formato estructurado (JSON o Markdown) que el agente usará como "fuente de verdad".
- [ ] Configurar la CLI básica (ej. comando `apply <url>`).
- [ ] Implementar el `FileManager`: 
  - [ ] Creación automática de la carpeta `data/postulaciones/`.
  - [ ] Función para inicializar y agregar filas al `tracking_postulaciones.csv`.
  - [ ] Función para crear carpetas por cargo y guardar archivos dummy de prueba.

## Fase 2: El Cerebro (LangGraph & LLM)
- [ ] Diseñar el `State` de LangGraph (Pydantic models para el contexto).
- [ ] Crear el nodo `analizar_oferta` (Input: Texto plano del trabajo -> Output: Keywords y Requisitos).
- [ ] Crear el nodo `adaptar_cv` (Prompts para ajustar el perfil base a los requerimientos).
- [ ] Crear el nodo `redactar_carta` (Cover letter).
- [ ] Crear el nodo `responder_preguntas` (Preguntas frecuentes de HR).
- [ ] Ensamblar el grafo y probar el flujo completo con datos "hardcodeados" de un trabajo.

## Fase 3: Integración de Plataformas (Scraping)
- [ ] Implementar módulo de extracción para **GetOnBrd** (Suele ser más amigable/estructurado).
- [ ] Implementar módulo de extracción para **MeetFrank**.
- [ ] Implementar módulo de extracción para **LinkedIn** (Considerar Playwright/Selenium para saltar bloqueos o usar APIs no oficiales con cuidado).

## Fase 4: Refinamiento y Autopiloto (Opcional)
- [ ] Implementar lógica para exportar el CV final de Markdown a PDF automáticamente.
- [ ] Human-in-the-loop: Pausar el grafo de LangGraph para que el usuario apruebe las respuestas y el CV antes de guardar/enviar.
- [ ] Script de automatización de clicks (Selenium/Playwright) para *enviar* la postulación automáticamente usando los datos generados.

## Fase 5: Multi Perfil y Estrategias de Búsqueda
- [ ] Soportar múltiples perfiles profesionales por usuario (ej: AI Engineer, Data Scientist, Data Engineer).
- [ ] Asociar múltiples CVs base según perfil objetivo.
- [ ] Permitir seleccionar perfil activo desde CLI.
- [ ] Permitir scouting y aplicación por perfil sin reescribir el perfil maestro completo.

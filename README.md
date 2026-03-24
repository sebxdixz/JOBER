# Jober CLI

Sistema autonomo multiagente (LangGraph) que busca, filtra y puede auto-postular a ofertas laborales desde la terminal. Todo corre local, sin backend propio. Disena perfiles, hace scouting y prepara CV + cover letter adaptados.

This is an early-stage OSS project. Expect breaking changes while the CLI stabilizes.

---

## Features

- Busqueda autonoma multi-plataforma (GetOnBrd, LinkedIn, MeetFrank).
- Onboarding conversacional para crear el perfil.
- Screening rapido antes de generar documentos.
- CV y cover letter adaptados en PDF.
- Multi-profile: perfiles separados con CVs, postulaciones y tracking.
- Tracking en CSV por perfil.

---

## Instalacion

```bash
git clone https://github.com/sebxdixz/JOBER.git
cd JOBER
pip install -e .
```

**IMPORTANTE:** Playwright no instala navegadores por defecto. Ejecuta:

```bash
playwright install chromium
```

**IMPORTANTE:** Para exportar PDFs premium via LaTeX necesitas `pdflatex` o `xelatex` en PATH
(TeX Live en Linux/macOS, MiKTeX en Windows). Si no estan presentes, JOBER usa el fallback HTML/ReportLab.

---

## Quickstart (ES)

```bash
jober init --profile ai
jober preset-ai --profile ai
jober login linkedin --profile ai
jober scout --limit 5 --per-platform 3 --profile ai
jober apply-scout --top 1 --profile ai
jober run --profile ai
```

---

## Quickstart (EN)

```bash
jober init --profile ai
jober preset-ai --profile ai
jober login linkedin --profile ai
jober scout --limit 5 --per-platform 3 --profile ai
jober apply-scout --top 1 --profile ai
jober run --profile ai
```

---

## Multi-profile

```bash
jober profile list
jober profile create data --copy-from ai
jober profile use data
jober profile info --profile data
```

Estructura local:

```text
~/.jober/
  .env
  profiles/
    <perfil>/
      perfil_maestro.json
      cv_base/
      postulaciones/
      tracking_postulaciones.csv
      last_scout.json
```

---

## Comandos principales

- `jober init --profile <id>`
- `jober scout --profile <id>`
- `jober apply "<url>" --profile <id>`
- `jober apply-scout --top 2 --profile <id>`
- `jober run --profile <id>`
- `jober tutorial`
- `jober doctor`

---

## Testing

```bash
pip install -e ".[dev]"
pytest -q
```

---

## Auto-apply: notas importantes

- `jober run` no es solo scouting: busca, filtra, genera documentos y luego intenta auto-postular.
- Al iniciar, `run` reutiliza candidatos del ultimo `scout` como warm start para llegar antes al intento de postulacion.
- Auto-apply es heuristico y puede fallar segun el formulario.
- Tiene modo ATS-specific para `Greenhouse` y `Lever`, con selectores y pasos mas agresivos.
- Tiene modo visual opcional para paginas dificiles usando screenshot + VLM + click por coordenadas.
- Si detecta campos requeridos no soportados, deja el estado como `preparado`.
- Estados importantes:
  - `applied`: hubo envio verificable.
  - `prepared`: se genero CV/cover y se intento postular, pero el formulario no era totalmente compatible o no hubo confirmacion fuerte.
  - `filtered`: se descarto antes de generar documentos.
  - `error`: fallo tecnico en scraping, pipeline o navegador.
- Respeta limites diarios y delays configurados en tu perfil.

UI local:

```bash
jober run --ui --ui-port 8765
```

La UI local muestra:
- estado del workflow en vivo
- carpeta fisica por oferta
- artefactos como `lead_snapshot.json`, `screening_result.json`, `run_trace.json`, `application_result.json`, `cv_adaptado.pdf`

Modo vision opcional:

```bash
$env:JOBER_VISION_MODE="1"
```

Si quieres separar el modelo visual del modelo principal, define tambien:

```bash
$env:VISION_MODEL="tu-modelo-vision"
$env:VISION_BASE_URL="https://tu-endpoint-openai-compatible"
$env:VISION_API_KEY="tu-api-key"
```

---

## Seguridad y responsabilidad

El uso de scraping y auto-apply puede violar Terminos de Servicio de algunas plataformas. Usa esta herramienta bajo tu propia responsabilidad.

---

## Contribuciones

PRs bienvenidos. Para cambios mayores, abre un issue primero.

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
git clone https://github.com/<tu-usuario>/jober-cli.git
cd jober-cli
pip install -e .
```

Opcional (solo si quieres export PDF via navegador):

```bash
playwright install chromium
```

Opcional (mejor calidad PDF via LaTeX):

- Instala `pdflatex` o `xelatex` y define en PATH.

---

## Quickstart (ES)

```bash
jober init --profile ai
jober preset-ai --profile ai
jober scout --limit 5 --per-platform 3 --profile ai
jober apply-scout --top 1 --profile ai
```

Modo autonomo:

```bash
jober run --profile ai
```

---

## Quickstart (EN)

```bash
jober init --profile ai
jober preset-ai --profile ai
jober scout --limit 5 --per-platform 3 --profile ai
jober apply-scout --top 1 --profile ai
```

Autonomous mode:

```bash
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

- Auto-apply es heuristico y puede fallar segun el formulario.
- Si detecta campos requeridos no soportados, deja el estado como `preparado`.
- Respeta limites diarios y delays configurados en tu perfil.

---

## Seguridad y responsabilidad

El uso de scraping y auto-apply puede violar Terminos de Servicio de algunas plataformas. Usa esta herramienta bajo tu propia responsabilidad.

---

## Contribuciones

PRs bienvenidos. Para cambios mayores, abre un issue primero.

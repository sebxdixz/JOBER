# Contributing

Gracias por querer contribuir a Jober. Esta guia es breve a proposito: el objetivo es facilitar PRs pequeños y utiles.

## Requisitos

- Python >= 3.11
- `pip install -e ".[dev]"`

## Flujo recomendado

1. Crea un branch desde `main`.
2. Haz cambios pequeños y enfocados.
3. Agrega tests si cambias comportamiento.
4. Ejecuta:

```bash
pytest -q
```

## Estilo

- Preferir cambios claros y directos.
- Mantener mensajes de error entendibles para CLI.
- Evitar dependencias nuevas salvo necesidad real.

## Reportes de bugs

Incluye:
- Comando exacto ejecutado
- Sistema operativo
- Salida completa del error
- Archivos relevantes si aplica (`~/.jober/profiles/<perfil>/`)

## Seguridad

No subir datos sensibles (API keys, CVs reales, etc.).

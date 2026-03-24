"""Local status server for showing live scout/apply progress and artifacts."""

from __future__ import annotations

import hashlib
import html
import json
import mimetypes
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, quote, unquote, urlparse

from jober.core.config import ensure_profile_dirs
from jober.utils.runtime_status import load_status


TEXT_SUFFIXES = {".json", ".md", ".txt", ".tex", ".log", ".csv"}


def _format_dt(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return value


def _escape(value: str | object) -> str:
    return html.escape(str(value or ""))


def _job_token(url: str) -> str:
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:12]


def _find_job(status: dict, job_url: str) -> dict | None:
    for job in status.get("jobs", []):
        if job.get("url") == job_url:
            return job
    return None


def _job_output_dir(profile_id: str, job: dict) -> Path | None:
    raw = str(job.get("output_dir") or "").strip()
    if not raw:
        return None

    try:
        output_dir = Path(raw).expanduser().resolve()
    except Exception:
        return None

    allowed_root = ensure_profile_dirs(profile_id).postulaciones_dir.resolve()
    try:
        output_dir.relative_to(allowed_root)
    except Exception:
        return None

    if not output_dir.exists() or not output_dir.is_dir():
        return None
    return output_dir


def _list_artifacts(profile_id: str, job: dict) -> list[Path]:
    output_dir = _job_output_dir(profile_id, job)
    if output_dir is None:
        return []
    preferred = [
        "lead_snapshot.json",
        "prefilter_result.json",
        "analysis_trace.json",
        "screening_result.json",
        "run_trace.json",
        "apply_trace.json",
        "pipeline_error.json",
        "oferta_original.json",
        "match_analysis.json",
        "application_result.json",
        "cv_adaptado.md",
        "cv_adaptado.pdf",
        "cv_adaptado.tex",
        "cover_letter.md",
        "cover_letter.pdf",
        "qa_respuestas.json",
    ]
    files = [path for path in output_dir.iterdir() if path.is_file()]
    preferred_map = {name: idx for idx, name in enumerate(preferred)}
    return sorted(
        files,
        key=lambda path: (preferred_map.get(path.name, len(preferred)), path.name.lower()),
    )


def _artifact_href(job: dict, artifact_name: str) -> str:
    return f"/artifact?url={quote(job.get('url', ''), safe='')}&name={quote(artifact_name, safe='')}"


def _job_detail_href(job: dict) -> str:
    return f"/job?url={quote(job.get('url', ''), safe='')}"


def _render_artifact_links(profile_id: str, job: dict, compact: bool = False) -> str:
    artifacts = _list_artifacts(profile_id, job)
    if not artifacts:
        return "<div class='artifact-empty'>Sin artefactos aun.</div>"

    if compact:
        artifacts = artifacts[:6]

    links = []
    for artifact in artifacts:
        links.append(
            f"<a class='artifact-chip' href='{_artifact_href(job, artifact.name)}'>{_escape(artifact.name)}</a>"
        )
    return "".join(links)


def _render_job_card(profile_id: str, job: dict) -> str:
    output_dir = _job_output_dir(profile_id, job)
    notes = _escape(job.get("notes", ""))
    detail_link = _job_detail_href(job)
    return f"""
    <div class="card">
      <div class="row">
        <div class="title">{_escape(job.get('title', '-'))}</div>
        <div class="badge">{_escape(job.get('status', '-'))}</div>
      </div>
      <div class="meta">
        <span>{_escape(job.get('company', '-'))}</span>
        <span>{_escape(job.get('location', '-'))}</span>
        <span>{_escape(job.get('platform', '-'))}</span>
      </div>
      <div class="url">{_escape(job.get('url', ''))}</div>
      {f"<div class='notes'>{notes}</div>" if notes else ""}
      <div class="trace">
        <div><strong>Carpeta:</strong> {f"<a class='detail-link' href='{detail_link}'>{_escape(output_dir)}</a>" if output_dir else "Sin carpeta aun"}</div>
        <div class="artifact-row">{_render_artifact_links(profile_id, job, compact=True)}</div>
      </div>
      <div class="actions">
        <a class="detail-link" href="{detail_link}">Ver detalle</a>
      </div>
      <div class="small">{_format_dt(job.get('updated_at', ''))}</div>
    </div>
    """


def _render_dashboard(status: dict) -> str:
    profile_id = status.get("profile_id", "-")
    mode = status.get("mode", "-")
    stage = status.get("stage", "-")
    message = status.get("message", "")
    updated_at = _format_dt(status.get("updated_at", ""))
    jobs = status.get("jobs", [])

    cards_html = "\n".join(_render_job_card(profile_id, job) for job in jobs)
    if not cards_html:
        cards_html = "<div class='empty'>Sin datos aun.</div>"

    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content="5" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Jober Live</title>
    <style>
      :root {{
        --bg: #f3efe6;
        --panel: #fffdf8;
        --ink: #18212f;
        --muted: #667085;
        --accent: #135d66;
        --accent-soft: #e8f3f2;
        --border: #dfd8c7;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        background:
          radial-gradient(circle at top left, rgba(19,93,102,0.08), transparent 28%),
          linear-gradient(180deg, #f6f2ea 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      .wrap {{
        max-width: 1100px;
        margin: 24px auto 64px;
        padding: 0 16px;
      }}
      .header {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 18px 22px;
        display: grid;
        gap: 10px;
        box-shadow: 0 18px 45px rgba(24,33,47,0.06);
      }}
      .header .row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
      }}
      .page-title {{
        font-size: 22px;
        font-weight: 800;
      }}
      .pill {{
        background: var(--accent);
        color: #fff;
        padding: 5px 12px;
        border-radius: 999px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }}
      .meta {{
        display: flex;
        gap: 12px;
        color: var(--muted);
        font-size: 14px;
        flex-wrap: wrap;
      }}
      .message {{
        color: var(--accent);
        font-weight: 700;
        font-size: 14px;
      }}
      .grid {{
        margin-top: 18px;
        display: grid;
        gap: 14px;
      }}
      .card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 16px 18px;
        display: grid;
        gap: 8px;
        box-shadow: 0 10px 28px rgba(24,33,47,0.04);
      }}
      .card .row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
      }}
      .title {{
        font-size: 17px;
        font-weight: 700;
      }}
      .badge {{
        background: var(--accent-soft);
        color: var(--accent);
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }}
      .url, .trace {{
        font-size: 12px;
        color: var(--muted);
        word-break: break-all;
      }}
      .notes {{
        padding: 10px 12px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        font-size: 13px;
        color: #334155;
      }}
      .artifact-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
      }}
      .artifact-chip, .detail-link, .back-link {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        border-radius: 999px;
        text-decoration: none;
        font-size: 12px;
        border: 1px solid var(--border);
        color: var(--accent);
        background: #fff;
      }}
      .detail-link, .back-link {{
        font-weight: 700;
      }}
      .artifact-empty {{
        color: var(--muted);
        font-size: 12px;
      }}
      .small {{
        font-size: 11px;
        color: var(--muted);
      }}
      .actions {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }}
      .empty {{
        padding: 28px;
        text-align: center;
        color: var(--muted);
        background: var(--panel);
        border: 1px dashed var(--border);
        border-radius: 16px;
      }}
      .detail {{
        margin-top: 18px;
        display: grid;
        gap: 14px;
      }}
      .detail-section {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 16px 18px;
        display: grid;
        gap: 10px;
      }}
      .detail-section h2 {{
        margin: 0;
        font-size: 16px;
      }}
      .detail-pre {{
        margin: 0;
        padding: 16px;
        border-radius: 14px;
        background: #141a26;
        color: #f8fafc;
        overflow: auto;
        font-size: 12px;
        line-height: 1.5;
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="header">
        <div class="row">
          <div class="page-title">Jober Live</div>
          <div class="pill">{_escape(mode)}</div>
        </div>
        <div class="meta">
          <span>Perfil: {_escape(profile_id)}</span>
          <span>Etapa: {_escape(stage)}</span>
          <span>Actualizado: {_escape(updated_at)}</span>
          <span><a class="detail-link" href="/status.json">status.json</a></span>
        </div>
        {f"<div class='message'>{_escape(message)}</div>" if message else ""}
      </div>
      <div class="grid">
        {cards_html}
      </div>
    </div>
  </body>
</html>
"""


def _render_job_detail(status: dict, job: dict) -> str:
    profile_id = status.get("profile_id", "-")
    output_dir = _job_output_dir(profile_id, job)
    artifacts = _list_artifacts(profile_id, job)
    notes = _escape(job.get("notes", ""))
    artifact_links = _render_artifact_links(profile_id, job, compact=False)

    payload_preview = json.dumps(job, indent=2, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content="5" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Jober Detail</title>
    <style>{_render_dashboard({'jobs': []}).split('<style>', 1)[1].split('</style>', 1)[0]}</style>
  </head>
  <body>
    <div class="wrap">
      <div class="header">
        <div class="row">
          <div class="page-title">{_escape(job.get('title', '-'))}</div>
          <div class="pill">{_escape(job.get('status', '-'))}</div>
        </div>
        <div class="meta">
          <span>{_escape(job.get('company', '-'))}</span>
          <span>{_escape(job.get('location', '-'))}</span>
          <span>{_escape(job.get('platform', '-'))}</span>
          <span>Actualizado: {_escape(_format_dt(job.get('updated_at', '')))}</span>
        </div>
        <div class="actions">
          <a class="back-link" href="/">Volver</a>
          <a class="detail-link" href="{_escape(job.get('url', ''))}">Oferta original</a>
        </div>
      </div>

      <div class="detail">
        <div class="detail-section">
          <h2>Traza fisica</h2>
          <div class="url">{_escape(output_dir) if output_dir else "Sin carpeta fisica asociada aun."}</div>
          {f"<div class='notes'>{notes}</div>" if notes else ""}
        </div>

        <div class="detail-section">
          <h2>Artefactos</h2>
          <div class="artifact-row">{artifact_links if artifacts else "Sin artefactos aun."}</div>
        </div>

        <div class="detail-section">
          <h2>Estado runtime</h2>
          <pre class="detail-pre">{_escape(payload_preview)}</pre>
        </div>
      </div>
    </div>
  </body>
</html>
"""


def _render_not_found(message: str) -> str:
    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Jober Live</title>
  </head>
  <body style="font-family:Segoe UI,Arial,sans-serif;padding:24px;">
    <p>{_escape(message)}</p>
    <p><a href="/">Volver</a></p>
  </body>
</html>
"""


def _guess_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    if path.suffix.lower() in TEXT_SUFFIXES:
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def _load_artifact(profile_id: str, status: dict, job_url: str, artifact_name: str) -> tuple[Path | None, bytes | None, str]:
    job = _find_job(status, job_url)
    if job is None:
        return None, None, "Oferta no encontrada."

    output_dir = _job_output_dir(profile_id, job)
    if output_dir is None:
        return None, None, "La oferta aun no tiene carpeta fisica."

    artifact_path = (output_dir / artifact_name).resolve()
    try:
        artifact_path.relative_to(output_dir)
    except Exception:
        return None, None, "Ruta de artefacto no valida."

    if not artifact_path.exists() or not artifact_path.is_file():
        return None, None, "Artefacto no encontrado."

    try:
        return artifact_path, artifact_path.read_bytes(), ""
    except Exception as exc:
        return None, None, f"No se pudo leer el artefacto: {exc}"


def _make_handler(profile_id: str):
    class StatusHandler(BaseHTTPRequestHandler):
        def _send_html(self, html_body: str, status_code: int = 200) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_body.encode("utf-8"))

        def _send_json(self, payload: dict, status_code: int = 200) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))

        def _send_bytes(self, content: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            status = load_status(profile_id)

            if parsed.path == "/status.json":
                self._send_json(status)
                return

            if parsed.path == "/job":
                job_url = unquote(params.get("url", [""])[0])
                job = _find_job(status, job_url)
                if job is None:
                    self._send_html(_render_not_found("No se encontro la oferta pedida."), status_code=404)
                    return
                self._send_html(_render_job_detail(status, job))
                return

            if parsed.path == "/artifact":
                job_url = unquote(params.get("url", [""])[0])
                artifact_name = unquote(params.get("name", [""])[0])
                artifact_path, content, error = _load_artifact(profile_id, status, job_url, artifact_name)
                if content is None or artifact_path is None:
                    self._send_html(_render_not_found(error or "Artefacto no encontrado."), status_code=404)
                    return
                self._send_bytes(content, _guess_content_type(artifact_path))
                return

            self._send_html(_render_dashboard(status))

        def log_message(self, format, *args):
            return

    return StatusHandler


def start_status_server(profile_id: str, port: int = 8765):
    ensure_profile_dirs(profile_id)
    handler = _make_handler(profile_id)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        return None

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def stop_status_server(server):
    if server is None:
        return
    try:
        server.shutdown()
        server.server_close()
    except Exception:
        pass

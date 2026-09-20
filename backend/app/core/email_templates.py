"""Jinja2 rendering for transactional emails — cf. app/templates/email/*.html.
Plain Jinja2 templates, not a React Email/MJML toolchain: this platform has no
frontend build step to plug one into (cf. backend-first sequencing), and these
are static HTML emails with a handful of variables, not a component library.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_email(template_name: str, **context) -> str:
    return _env.get_template(template_name).render(**context)

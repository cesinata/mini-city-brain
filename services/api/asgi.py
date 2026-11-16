"""Entry point for uvicorn: `uvicorn services.api.asgi:app`."""

from services.api.main import build_default_app

app = build_default_app()

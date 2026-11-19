"""Публичный общий журнал: отдельная пустая база и постоянный секрет сессии."""
import os
import secrets
from pathlib import Path
from app import create_app


def create_public_app():
    folder = Path(__file__).resolve().parent / "instance"
    folder.mkdir(exist_ok=True)
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        secret_file = folder / "session.key"
        # Режим x не перезаписывает существующий ключ при перезапуске.
        try:
            with secret_file.open("x", encoding="ascii") as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = secret_file.read_text(encoding="ascii").strip()
        if not secret:
            raise RuntimeError("Пустой ключ сессии: проверьте instance/session.key.")
    app = create_app(folder / "public.db", shared=True)
    app.config.update(SECRET_KEY=secret, SESSION_COOKIE_SECURE=True)
    return app


application = create_public_app()

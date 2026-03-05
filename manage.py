"""
Утилита команд разработчика/админа для проекта Vitrina.

Примеры:
    python manage.py run        # запустить dev-сервер
    python manage.py migrate    # применить миграции Alembic
    python manage.py test       # запустить pytest
"""
import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> int:
    """Запускает подкоманду в корне проекта."""
    print(">", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    return proc.returncode


def cmd_run(args: argparse.Namespace) -> int:
    """Запуск dev-сервера uvicorn."""
    host = args.host
    port = str(args.port)
    reload_flag = ["--reload"] if args.reload else []
    return _run([sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", port, *reload_flag])


def cmd_migrate(_: argparse.Namespace) -> int:
    """Применить миграции Alembic (upgrade head)."""
    return _run([sys.executable, "-m", "alembic", "upgrade", "head"])


def cmd_test(_: argparse.Namespace) -> int:
    """Запустить тесты pytest."""
    return _run([sys.executable, "-m", "pytest", "tests"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manage.py", description="Утилита для управления проектом Vitrina")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_run = subparsers.add_parser("run", help="Запустить dev-сервер uvicorn")
    p_run.add_argument("--host", default="127.0.0.1", help="Хост (по умолчанию 127.0.0.1)")
    p_run.add_argument("--port", type=int, default=8000, help="Порт (по умолчанию 8000)")
    p_run.add_argument("--no-reload", dest="reload", action="store_false", help="Выключить авто-перезапуск")
    p_run.set_defaults(func=cmd_run, reload=True)

    p_migrate = subparsers.add_parser("migrate", help="Применить миграции Alembic (upgrade head)")
    p_migrate.set_defaults(func=cmd_migrate)

    p_test = subparsers.add_parser("test", help="Запустить pytest")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())


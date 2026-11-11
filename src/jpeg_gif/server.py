"""Запуск приложения и выбор слоя хранения данных."""

import argparse
from pathlib import Path

from jpeg_gif.file_store import FileStore
from jpeg_gif.http_api import AppServer
from jpeg_gif.jobs import Jobs
from jpeg_gif.model import Model


def create_store(backend, root):
    """Выбрать файловый слой этапа 2 или SQLite через PonyORM этапа 3."""
    if backend == "sqlite":
        from jpeg_gif.pony_store import PonyStore
        return PonyStore(Path(root) / "records.sqlite3")
    return FileStore(Path(root) / "records.json")


def main():
    """Открыть сервер; при Ctrl+C завершить очередь и закрыть данные."""
    parser = argparse.ArgumentParser(description="JPEG to GIF HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--backend", choices=["file", "sqlite"], default="sqlite",
    )
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    store = create_store(args.backend, args.data_dir)
    model = Model(store)
    jobs = Jobs(model, args.data_dir, args.test_mode)
    try:
        with AppServer((args.host, args.port), model, jobs) as server:
            print(f"API: http://{args.host}:{server.server_port}")
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            jobs.close()
        finally:
            store.close()


if __name__ == "__main__":
    main()

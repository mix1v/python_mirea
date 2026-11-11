"""Изолированный сервер на свободном TCP-порту для модельных тестов."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from jpeg_gif.client import ApiClient
from jpeg_gif.http_api import AppServer
from jpeg_gif.jobs import Jobs
from jpeg_gif.model import Model
from jpeg_gif.server import create_store


class RunningApi:
    """Открыть отдельные данные и сервер, затем освободить все ресурсы."""

    def __init__(self, backend="file", test_mode=True):
        self.folder = TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.store = create_store(backend, self.root)
        self.model = Model(self.store)
        self.jobs = Jobs(self.model, self.root, test_mode)
        self.server = AppServer(("127.0.0.1", 0), self.model, self.jobs)
        self.thread = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01},
        )
        self.thread.start()
        self.client = ApiClient(port=self.server.server_port)

    def settle(self):
        """Дождаться очереди, не подменяя обращения к HTTP API."""
        self.jobs.queue.join()

    def close(self):
        """Остановить HTTP, закончить задания и удалить временные данные."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.jobs.close()
        self.store.close()
        self.folder.cleanup()

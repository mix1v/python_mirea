"""Фоновая очередь с запуском файлового конвертера через subprocess."""

import base64
import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread

from jpeg_gif.schema import DomainError


TIMEOUT_SECONDS = 60


def input_file(root, payload):
    """Разрешить только путь к файлу внутри папки inbox сервера."""
    try:
        value = json.loads(payload)
        source = value["source"]
        if not isinstance(source, str) or not source:
            raise ValueError("Source must be a nonempty string")
        inbox = (Path(root) / "inbox").resolve()
        path = (inbox / source).resolve()
        path.relative_to(inbox)
        return path
    except (ValueError, KeyError, TypeError) as error:
        raise DomainError(
            "Payload must contain a source inside inbox") from error


class Jobs:
    """Принимать задания без ожидания завершения преобразования."""

    def __init__(self, model, root, test_mode=False):
        self.model = model
        self.root = Path(root).resolve()
        (self.root / "inbox").mkdir(parents=True, exist_ok=True)
        (self.root / "outbox").mkdir(exist_ok=True)
        self.test_mode = test_mode
        self.errors = []
        self.queue = Queue()
        self.thread = Thread(target=self._loop, daemon=True)
        self.thread.start()
        self._recover()

    def _recover(self):
        """Продолжить незавершённые задания после перезапуска сервера."""
        for row in self.model.store.read("assignment"):
            if row["state"] in {"queued", "running"}:
                responses = self.model.response_dump(row["key"], {})
                if responses:
                    self.model.store.update("assignment", row["key"], {
                        "state": responses[-1]["state"], "enqueued": 0,
                    })
                else:
                    self.queue.put(row)

    def submit(self, values):
        """Проверить payload до сохранения и вернуть принятое задание."""
        input_file(self.root, values.get("payload", ""))
        row = self.model.assignment_add(values)
        self.queue.put(row)
        return row

    def _loop(self):
        """Обрабатывать очередь одним потоком до служебного маркера."""
        while True:
            row = self.queue.get()
            try:
                if row is None:
                    return
                self._execute(row)
            except Exception as error:
                self.errors.append(error)
            finally:
                self.queue.task_done()

    def _execute(self, row):
        """Записать результат, ошибку CLI или отметку тестового режима."""
        if self.test_mode:
            self.model.finish(row["key"], state="skipped")
            return
        self.model.store.update("assignment", row["key"], {"state": "running"})
        try:
            result = self._convert(row)
            self.model.finish(row["key"], response=result)
        except (OSError, subprocess.SubprocessError, DomainError) as error:
            self.model.finish(row["key"], error=str(error), state="failed")

    def _convert(self, row):
        source = input_file(self.root, row["payload"])
        target = self.root / "outbox" / f"{row['key']}.gif"
        subprocess.run(
            [sys.executable, "-m", "jpeg_gif.convert",
                str(source), str(target)],
            check=True, capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS,
        )
        encoded = base64.b64encode(target.read_bytes()).decode("ascii")
        return json.dumps({"file": f"outbox/{target.name}", "gif": encoded})

    def close(self):
        """Завершить очередь до закрытия хранилища."""
        self.queue.put(None)
        self.queue.join()
        self.thread.join()
        if self.errors:
            raise RuntimeError("Background worker failed") from self.errors[0]

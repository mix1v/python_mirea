"""Первый слой данных: таблицы в JSON, атомарная замена файла."""

import json
from pathlib import Path
from threading import RLock
import time

from jpeg_gif.schema import SCHEMA


REPLACE_ATTEMPTS = 10
REPLACE_DELAY_SECONDS = 0.05


class FileStore:
    """Хранить ER-записи в одном файле под блокировкой потоков."""

    def __init__(self, filename):
        self.path = Path(filename)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.tables = {name: [] for name in SCHEMA}
        if self.path.exists():
            self.tables = json.loads(self.path.read_text("utf-8"))

    def read(self, table):
        """Вернуть копии записей, не раскрывая изменяемое хранилище."""
        with self.lock:
            return [dict(row) for row in self.tables[table]]

    def insert(self, table, values):
        """Назначить следующий ключ и сохранить запись на диск."""
        with self.lock:
            keys = [row["key"] for row in self.tables[table]]
            row = dict(values, key=max(keys, default=0) + 1)
            self.tables[table].append(row)
            self._save()
            return dict(row)

    def update(self, table, key, values):
        """Изменить служебные поля задания при обработке очереди."""
        with self.lock:
            row = next(item for item in self.tables[table]
                       if item["key"] == key)
            row.update(values)
            self._save()

    def _save(self):
        """Не оставлять частично записанный JSON при прерывании записи."""
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.tables), "utf-8")
        self._replace(temporary)

    def _replace(self, temporary):
        """Повторить замену при краткой блокировке файла Windows."""
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                temporary.replace(self.path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(REPLACE_DELAY_SECONDS)

    def close(self):
        """У файлового слоя нет постоянно открытого соединения."""

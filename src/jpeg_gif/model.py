"""Операции предметной модели, общие для файлового и ORM-слоёв."""

import time
from threading import RLock

from jpeg_gif.schema import DomainError, REPORT_WINDOW, filters, new_record


class Model:
    """Контролировать связи и выполнять операции таблицы 9."""

    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        self.lock = RLock()

    def _dump(self, table, values):
        criteria = filters(table, values)
        return [row for row in self.store.read(table)
                if all(row[name] == value
                       for name, value in criteria.items())]

    def _retrieve(self, table, key):
        rows = self._dump(table, {"key": key})
        if not rows:
            raise DomainError("Record not found", 404)
        return rows[0]

    def individual_add(self, values):
        """Создать Individual с серверным ключом и временем Unix."""
        with self.lock:
            return self.store.insert(
                "individual", new_record("individual", values),
            )

    def individual_dump(self, values):
        """Найти Individual по точному совпадению переданных полей."""
        return self._dump("individual", values)

    def individual_retrieve(self, key):
        """Прочитать один Individual по ключу."""
        return self._retrieve("individual", key)

    def assignment_add(self, values):
        """Создать задание с существующим Individual и статусом queued."""
        with self.lock:
            data = new_record("assignment", values)
            self.individual_retrieve(data["individual"])
            data.update(state="queued", enqueued=1)
            return self.store.insert("assignment", data)

    def assignment_dump(self, individual, values):
        """Найти задания указанного Individual по дополнительным полям."""
        return self._dump("assignment", dict(values, individual=individual))

    def assignment_retrieve(self, key):
        """Прочитать одно задание по ключу."""
        return self._retrieve("assignment", key)

    def response_dump(self, assignment, values):
        """Найти ответы, относящиеся к указанному заданию."""
        return self._dump("response", dict(values, assignment=assignment))

    def response_retrieve(self, key):
        """Прочитать один ответ по ключу."""
        return self._retrieve("response", key)

    def finish(self, key, response="", error="", state="done"):
        """Атомарно относительно модели зафиксировать итог обработки."""
        with self.lock:
            row = new_record("response", {
                "assignment": key, "response": response,
                "error": error, "state": state,
            })
            self.store.insert("response", row)
            self.store.update("assignment", key, {
                "state": state, "enqueued": 0,
            })

    def report_dump(self):
        """Правое соединение с недавними ответами и проекция по (9)."""
        threshold = int(self.clock()) - REPORT_WINDOW
        assignments = {row["key"]: row["payload"]
                       for row in self.store.read("assignment")}
        rows = [
            {"payload": assignments.get(row["assignment"]),
             "error": row["error"], "response": row["response"]}
            for row in self.store.read("response")
            if row["timestamp"] >= threshold
        ]
        unique = {tuple(row.items()): row for row in rows}
        return list(unique.values())

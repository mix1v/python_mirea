"""Поля ER-диаграммы и проверка параметров модели."""

import time


SCHEMA = {
    "individual": {
        "key": int, "timestamp": int, "ip": str, "locale": str,
        "platform": str, "user_agent": str,
    },
    "assignment": {
        "key": int, "timestamp": int, "payload": str, "individual": int,
        "state": str, "enqueued": int,
    },
    "response": {
        "key": int, "timestamp": int, "response": str, "state": str,
        "error": str, "assignment": int, "cache_hit": int,
    },
}
REPORT_WINDOW = 9 * 60


class DomainError(Exception):
    """Ошибка параметров или отсутствующая связанная запись."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def integer(value):
    """Прочитать целое без неявного округления и логических значений."""
    if isinstance(value, bool):
        raise DomainError("Boolean is not an integer parameter")
    try:
        return int(str(value))
    except (ValueError, TypeError) as error:
        raise DomainError("Expected an integer") from error


def filters(table, values):
    """Допускать только известные поля и приводить числовые параметры."""
    if values.keys() - SCHEMA[table].keys():
        raise DomainError("Unknown field")
    return {
        name: integer(value) if SCHEMA[table][name] is int else str(value)
        for name, value in values.items()
    }


def new_record(table, values):
    """Заполнить поля по умолчанию; первичный ключ назначает хранилище."""
    data = filters(table, values)
    if "key" in data:
        raise DomainError("Key is assigned by the server")
    result = {name: kind() for name, kind in SCHEMA[table].items()}
    result.pop("key")
    result["timestamp"] = int(time.time())
    result.update(data)
    return result

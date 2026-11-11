"""Клиент HTTP API с именами методов таблица_действие."""

from http.client import HTTPConnection
from http import HTTPStatus
import json
from urllib.parse import urlencode


DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en",
}


class ApiError(Exception):
    """Сохранить HTTP-код и сообщение сервера для вызывающего кода."""

    def __init__(self, status, data):
        super().__init__(data["error"])
        self.status = status


class ApiClient:
    """Работать по TCP, не обращаться к модели сервера напрямую."""

    def __init__(self, host="127.0.0.1", port=8000):
        self.host = host
        self.port = port

    def request(self, method, path, values=None, headers=None):
        """Вернуть код и JSON; headers={} отправляет запрос без заголовков."""
        query = urlencode(values or {})
        url = f"{path}?{query}" if query else path
        actual_headers = DEFAULT_HEADERS if headers is None else headers
        connection = HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request(method, url, headers=actual_headers)
            reply = connection.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            connection.close()

    def _call(self, method, path, values=None):
        status, data = self.request(method, path, values)
        if status != HTTPStatus.OK:
            raise ApiError(status, data)
        return data

    def individual_add(self, values):
        """POST /api/add-individual, параметры в строке запроса."""
        return self._call("POST", "/api/add-individual", values)

    def individual_dump(self, values=None):
        """GET /api/dump-individual с точными фильтрами."""
        return self._call("GET", "/api/dump-individual", values)

    def individual_retrieve(self, key):
        """GET /api/retrieve-individual по ключу."""
        return self._call("GET", "/api/retrieve-individual", {"key": key})

    def assignment_add(self, values):
        """POST /api/add-assignment; результат конвертации приходит позже."""
        return self._call("POST", "/api/add-assignment", values)

    def assignment_dump(self, individual, values=None):
        """GET /api/dump-assignment/:individual с точными фильтрами."""
        path = f"/api/dump-assignment/{individual}"
        return self._call("GET", path, values)

    def assignment_retrieve(self, key):
        """GET /api/retrieve-assignment по ключу."""
        return self._call("GET", "/api/retrieve-assignment", {"key": key})

    def response_dump(self, assignment, values=None):
        """GET /api/dump-response/:assignment с точными фильтрами."""
        return self._call("GET", f"/api/dump-response/{assignment}", values)

    def response_retrieve(self, key):
        """GET /api/retrieve-response по ключу."""
        return self._call("GET", "/api/retrieve-response", {"key": key})

    def report_dump(self):
        """GET /api/dump-report за последние девять минут."""
        return self._call("GET", "/api/dump-report")

"""Девять маршрутов варианта 9 на BaseHTTPRequestHandler."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import HTTPStatus
import json
import re
from urllib.parse import parse_qs, urlsplit

from jpeg_gif.schema import DomainError, integer


REQUIRED_HEADERS = (
    ({"POST", "PUT", "PATCH"}, "Content-Type", "application/json", 415),
    (None, "Accept", "application/json", 406),
    (None, "Accept-Language", "en", 406),
)
ROUTES = (
    ("POST", r"/api/add-individual", "individual_add"),
    ("GET", r"/api/dump-individual", "individual_dump"),
    ("GET", r"/api/retrieve-individual", "individual_retrieve"),
    ("POST", r"/api/add-assignment", "assignment_add"),
    ("GET", r"/api/dump-assignment/(?P<individual>\d+)", "assignment_dump"),
    ("GET", r"/api/retrieve-assignment", "assignment_retrieve"),
    ("GET", r"/api/dump-response/(?P<assignment>\d+)", "response_dump"),
    ("GET", r"/api/retrieve-response", "response_retrieve"),
    ("GET", r"/api/dump-report", "report_dump"),
)


def query_values(query):
    """Не принимать неоднозначные повторяющиеся параметры."""
    values = parse_qs(query, keep_blank_values=True)
    if any(len(items) != 1 for items in values.values()):
        raise DomainError("Repeated query parameter")
    return {name: items[0] for name, items in values.items()}


class Handler(BaseHTTPRequestHandler):
    """Проверять заголовки до маршрутизации и всегда отвечать JSON."""

    def _handle(self):
        try:
            self._headers()
            path = urlsplit(self.path)
            values = query_values(path.query)
            result = self._dispatch(path.path, values)
            self._reply(HTTPStatus.OK, result)
        except DomainError as error:
            self._reply(error.status, {"error": str(error)})

    def _headers(self):
        for methods, header, expected, status in REQUIRED_HEADERS:
            if methods is None or self.command in methods:
                if self.headers.get(header) != expected:
                    raise DomainError(f"Required {header}: {expected}", status)

    def _dispatch(self, path, values):
        for method, pattern, operation in ROUTES:
            match = re.fullmatch(pattern, path)
            if method == self.command and match:
                return self._invoke(operation, match.groupdict(), values)
        raise DomainError("Route not found", 404)

    def _invoke(self, operation, path_values, values):
        if operation == "assignment_add":
            return self.server.jobs.submit(values)
        function = getattr(self.server.model, operation)
        if operation.endswith("_retrieve"):
            if set(values) != {"key"}:
                raise DomainError("Exactly one key parameter is required")
            return function(integer(values["key"]))
        if path_values:
            parent = integer(next(iter(path_values.values())))
            return function(parent, values)
        if operation == "report_dump":
            if values:
                raise DomainError("Report does not accept query parameters")
            return function()
        return function(values)

    def _reply(self, status, value):
        encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format_string, *args):
        """Не засорять вывод тестов стандартным журналом HTTP-сервера."""

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle


class AppServer(ThreadingHTTPServer):
    """Передавать модель и очередь обработчикам HTTP-запросов."""

    def __init__(self, address, model, jobs):
        self.model = model
        self.jobs = jobs
        super().__init__(address, Handler)

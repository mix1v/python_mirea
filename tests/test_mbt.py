"""Покрытие HTTP API только переходами RuleBasedStateMachine."""

from http import HTTPStatus
import json
import os
import time

from hypothesis import settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine, initialize, invariant, rule,
)

from jpeg_gif.client import ApiError, DEFAULT_HEADERS
from support import RunningApi


TEXT = st.text(alphabet="abc XYZабв012_-", max_size=12)
CLOCK_TOLERANCE = 2
ROUTE_CASES = (
    ("POST", "/api/add-individual"),
    ("GET", "/api/dump-individual"),
    ("GET", "/api/retrieve-individual"),
    ("POST", "/api/add-assignment"),
    ("GET", "/api/dump-assignment/1"),
    ("GET", "/api/retrieve-assignment"),
    ("GET", "/api/dump-response/1"),
    ("GET", "/api/retrieve-response"),
    ("GET", "/api/dump-report"),
)


def without_time(row):
    """Исключить серверные часы из сравнения с независимым эталоном."""
    return {name: value for name, value in row.items()
            if name != "timestamp"}


class ApiMachine(RuleBasedStateMachine):
    """Сравнивать сетевой API с таблицами-словарями после переходов."""

    def __init__(self):
        super().__init__()
        self.api = RunningApi(os.environ.get("TEST_BACKEND", "file"))
        self.client = self.api.client
        self.people = []
        self.tasks = []
        self.answers = []

    @initialize(text=TEXT)
    def seed(self, text):
        """Любой сгенерированный сценарий проходит все девять маршрутов."""
        self.add_individual(text)
        self.add_assignment(0, text)
        self.read_existing(0)
        self.check_lists()
        self.client.report_dump()
        self.header_matrix()
        self.bad_queries()

    @rule(text=TEXT)
    def add_individual(self, text):
        """Сохранить входные поля и сверить назначение ключа."""
        fields = {"ip": "127.0.0.1", "locale": "en", "platform": text,
                  "user_agent": "MBT"}
        row = self.client.individual_add(fields)
        expected = dict(fields, key=len(self.people) + 1)
        assert without_time(row) == expected
        assert abs(row["timestamp"] - int(time.time())) <= CLOCK_TOLERANCE
        self.people.append(expected)

    @rule(index=st.integers(min_value=0, max_value=50), text=TEXT)
    def add_assignment(self, index, text):
        """Проверить связь задания и ответ тестового режима."""
        person = self.people[index % len(self.people)]
        payload = json.dumps({"source": f"{text or 'input'}.jpg"})
        values = {"individual": person["key"], "payload": payload}
        row = self.client.assignment_add(values)
        expected = dict(values, key=len(self.tasks) + 1,
                        state="queued", enqueued=1)
        assert without_time(row) == expected
        expected.update(state="skipped", enqueued=0)
        self.tasks.append(expected)
        self.api.settle()
        answer = {"key": len(self.answers) + 1, "assignment": row["key"],
                  "response": "", "error": "", "state": "skipped",
                  "cache_hit": 0}
        self.answers.append(answer)

    @rule(index=st.integers(min_value=0, max_value=50))
    def read_existing(self, index):
        """Проверить все три операции чтения записи по ключу."""
        cases = (
            (self.people, self.client.individual_retrieve),
            (self.tasks, self.client.assignment_retrieve),
            (self.answers, self.client.response_retrieve),
        )
        for rows, retrieve in cases:
            expected = rows[index % len(rows)]
            assert without_time(retrieve(expected["key"])) == expected

    @rule(text=TEXT)
    def filter_people(self, text):
        """Сопоставить результаты поиска с независимым фильтром."""
        expected = [row for row in self.people if row["platform"] == text]
        actual = self.client.individual_dump({"platform": text})
        assert [without_time(row) for row in actual] == expected

    @rule()
    def header_matrix(self):
        """Проверить порядок отсутствующих и неверных заголовков."""
        for method, path in ROUTE_CASES:
            self.check_route_headers(method, path)
        status, data = self.client.request("POST", "/api/no-route", headers={})
        assert status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert "Content-Type" in data["error"]

    def check_route_headers(self, method, path):
        """Перебрать ошибки отдельных заголовков одного маршрута."""
        required = ["Accept", "Accept-Language"]
        if method == "POST":
            required.insert(0, "Content-Type")
        for name in required:
            for bad in (None, "wrong"):
                headers = dict(DEFAULT_HEADERS)
                headers.pop(name)
                if bad is not None:
                    headers[name] = bad
                status, data = self.client.request(
                    method, path, headers=headers,
                )
                expected = (HTTPStatus.UNSUPPORTED_MEDIA_TYPE
                            if name == "Content-Type"
                            else HTTPStatus.NOT_ACCEPTABLE)
                assert status == expected
                assert name in data["error"]

    @rule()
    def bad_queries(self):
        """Проверить ошибочные параметры, связи и неизвестные маршруты."""
        cases = (
            ("GET", "/absent", {}, HTTPStatus.NOT_FOUND),
            ("GET", "/api/retrieve-individual", {}, HTTPStatus.BAD_REQUEST),
            ("GET", "/api/retrieve-individual", {"key": "x"},
             HTTPStatus.BAD_REQUEST),
            ("GET", "/api/retrieve-assignment", {"key": 99999},
             HTTPStatus.NOT_FOUND),
            ("GET", "/api/retrieve-response", {"key": 99999},
             HTTPStatus.NOT_FOUND),
            ("GET", "/api/dump-individual", {"unknown": "x"},
             HTTPStatus.BAD_REQUEST),
            ("GET", "/api/dump-report", {"key": 1}, HTTPStatus.BAD_REQUEST),
            ("POST", "/api/add-individual", {"key": 1},
             HTTPStatus.BAD_REQUEST),
        )
        for method, path, values, expected in cases:
            status, _ = self.client.request(method, path, values)
            assert status == expected
        self.bad_assignments()
        self.repeated_parameter()

    def bad_assignments(self):
        """Некорректное задание не должно попадать в очередь."""
        for payload in ("", "{}", "[]", '{"source":"../secret.jpg"}'):
            status, _ = self.client.request("POST", "/api/add-assignment", {
                "individual": 1, "payload": payload,
            })
            assert status == HTTPStatus.BAD_REQUEST
        status, _ = self.client.request("POST", "/api/add-assignment", {
            "individual": 99999, "payload": '{"source":"test.jpg"}',
        })
        assert status == HTTPStatus.NOT_FOUND

    def repeated_parameter(self):
        """Повтор ключа не должен молча менять смысл запроса."""
        status, _ = self.client.request(
            "GET", "/api/retrieve-individual?key=1&key=2",
        )
        assert status == HTTPStatus.BAD_REQUEST
        try:
            self.client.response_retrieve(99999)
        except ApiError as error:
            assert error.status == HTTPStatus.NOT_FOUND
        else:
            raise AssertionError("Expected client ApiError")

    @invariant()
    def check_lists(self):
        """Списки и проекция отчёта должны соответствовать эталону."""
        actual = self.client.individual_dump()
        assert [without_time(row) for row in actual] == self.people
        self.check_tasks()
        self.check_answers()
        expected_report = {row["payload"] for row in self.tasks}
        actual_report = self.client.report_dump()
        assert {row["payload"] for row in actual_report} == expected_report
        assert all(row["error"] == row["response"] == ""
                   for row in actual_report)

    def check_tasks(self):
        """Каждый родитель должен видеть только свои задания."""
        for person in self.people:
            expected = [row for row in self.tasks
                        if row["individual"] == person["key"]]
            actual = self.client.assignment_dump(person["key"])
            assert [without_time(row) for row in actual] == expected

    def check_answers(self):
        """Каждое задание должно видеть только свои ответы."""
        for task in self.tasks:
            actual = self.client.response_dump(task["key"])
            expected = [row for row in self.answers
                        if row["assignment"] == task["key"]]
            assert [without_time(row) for row in actual] == expected

    def teardown(self):
        """Закрывать сервер и базу даже при найденном контрпримере."""
        self.api.close()


TestApi = ApiMachine.TestCase
TestApi.settings = settings(
    max_examples=12, stateful_step_count=16, deadline=None,
    derandomize=True,
)

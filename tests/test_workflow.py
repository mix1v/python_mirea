"""Сгенерированные проверки реального CLI, очереди и отчёта API."""

import base64
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
from PIL import Image

from jpeg_gif.jobs import Jobs
from jpeg_gif.model import Model
from jpeg_gif.server import create_store
from support import RunningApi


WAIT_SECONDS = 10
FIXED_NOW = 2_000_000_000
WINDOW_SECONDS = 9 * 60


def backend():
    """Тот же слой данных, что выбран для модельного прогона."""
    return os.environ.get("TEST_BACKEND", "file")


def add_task(api):
    """Создать пользователя и задание через сетевой клиент."""
    person = api.client.individual_add({"platform": "integration"})
    return api.client.assignment_add({
        "individual": person["key"],
        "payload": json.dumps({"source": "input.jpg"}),
    })


def delayed_converter(entered, release):
    """Удержать работника до проверки немедленного HTTP-ответа."""
    original = Jobs._convert

    def convert(job, row):
        """После сигнала продолжить настоящее файловое преобразование."""
        entered.set()
        if not release.wait(WAIT_SECONDS):
            raise OSError("Test did not release the worker")
        return original(job, row)

    return convert


@settings(max_examples=5, deadline=None, derandomize=True)
@given(width=st.integers(1, 80), height=st.integers(1, 80),
       color=st.tuples(st.integers(0, 255), st.integers(0, 255),
                       st.integers(0, 255)))
def test_real_async_conversion(width, height, color):
    """HTTP возвращается, пока работник заблокирован; затем CLI пишет GIF."""
    api = RunningApi(backend(), test_mode=False)
    entered, release = Event(), Event()
    source = api.root / "inbox" / "input.jpg"
    Image.new("RGB", (width, height), color).save(source, "JPEG")
    try:
        delayed = delayed_converter(entered, release)
        with patch.object(Jobs, "_convert", delayed):
            task = add_task(api)
            assert task["state"] == "queued"
            assert entered.wait(WAIT_SECONDS)
            assert api.client.response_dump(task["key"]) == []
            assert api.client.assignment_retrieve(task["key"])[
                "state"] == "running"
            release.set()
            api.settle()
        answer = api.client.response_dump(task["key"])[0]
        assert answer["state"] == "done"
        result = json.loads(answer["response"])
        data = base64.b64decode(result["gif"], validate=True)
        assert data == (api.root / result["file"]).read_bytes()
        with Image.open(BytesIO(data)) as image:
            assert image.format == "GIF"
            assert image.size == (width, height)
    finally:
        release.set()
        api.close()


@settings(max_examples=3, deadline=None, derandomize=True)
@given(problem=st.sampled_from(["missing", "png", "broken"]))
def test_conversion_error(problem):
    """Неверный или отсутствующий JPEG создаёт доступный через API ответ."""
    api = RunningApi(backend(), test_mode=False)
    source = api.root / "inbox" / "input.jpg"
    try:
        if problem == "png":
            Image.new("RGB", (3, 3)).save(source, "PNG")
        elif problem == "broken":
            source.write_bytes(b"not a JPEG")
        task = add_task(api)
        api.settle()
        answer = api.client.response_dump(task["key"])[0]
        assert answer["state"] == "failed"
        assert answer["error"]
        assert answer["response"] == ""
        actual = api.client.assignment_retrieve(task["key"])
        assert actual["state"] == "failed"
        assert actual["enqueued"] == 0
    finally:
        api.close()


def report_rows(api, ages):
    """Заполнить фиксированные часы ответов для проверки границы окна."""
    expected = []
    for index, age in enumerate(ages):
        task = add_task(api)
        api.settle()
        answer = api.client.response_dump(task["key"])[0]
        values = {"timestamp": FIXED_NOW - age,
                  "error": f"error-{index}", "response": f"result-{index}"}
        api.store.update("response", answer["key"], values)
        if age <= WINDOW_SECONDS:
            expected.append({"payload": task["payload"],
                             "error": values["error"],
                             "response": values["response"]})
    return expected


@settings(max_examples=5, deadline=None, derandomize=True)
@given(extra=st.integers(min_value=0, max_value=1000))
def test_report_boundary(extra):
    """Ровно девять минут включаются, более старый ответ исключается."""
    api = RunningApi(backend())
    try:
        api.model.clock = lambda: FIXED_NOW
        expected = report_rows(api, [0, 539, 540, 541, extra])
        assert api.client.report_dump() == expected
        api.model.assignment_add({"individual": 1, "payload": "no answer"})
        assert api.client.report_dump() == expected
        duplicate = api.store.read("response")[0]
        duplicate.pop("key")
        api.store.insert("response", duplicate)
        assert api.client.report_dump() == expected
    finally:
        api.close()


@settings(max_examples=3, deadline=None, derandomize=True)
@given(state=st.sampled_from(["queued", "running", "partial"]))
def test_restart_recovery(state):
    """Незавершённая очередь и записи переживают закрытие хранилища."""
    with TemporaryDirectory() as folder:
        store = create_store(backend(), folder)
        model = Model(store)
        person = model.individual_add({"platform": "restart"})
        task = model.assignment_add({"individual": person["key"],
                                     "payload": '{"source":"input.jpg"}'})
        if state == "partial":
            model.finish(task["key"], state="skipped")
            store.update("assignment", task["key"], {"state": "running"})
        else:
            store.update("assignment", task["key"], {"state": state})
        store.close()
        verify_recovery(folder, task)


def verify_recovery(folder, task):
    """После открытия получить один ответ и согласованное состояние."""
    store = create_store(backend(), folder)
    model = Model(store)
    jobs = Jobs(model, Path(folder), test_mode=True)
    try:
        jobs.queue.join()
        answers = model.response_dump(task["key"], {})
        assert len(answers) == 1
        actual = model.assignment_retrieve(task["key"])
        assert actual["state"] == "skipped"
        assert actual["enqueued"] == 0
    finally:
        jobs.close()
        store.close()

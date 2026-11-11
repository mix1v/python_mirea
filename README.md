# Преобразование JPEG в GIF

Практическая работа № 2, вариант 9, ИКБО-71-24.
Тема курсовой: веб-приложение с HTTP API для асинхронного
преобразования файлов из формата JPEG в формат GIF.

## Этап 1. Файловый конвертер

Требуется Python 3.10 или новее. Установка из корня проекта:

```console
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
```

Сборка пакета: `python -m pip wheel . --no-deps -w dist`.

```console
jpeg-to-gif photo.jpg result.gif
python -m jpeg_gif.convert photo.jpg result.gif
run.bat demo
run.bat test
```

Утилита читает JPEG из файла и сохраняет GIF на диск. EXIF-поворот
применяется до преобразования. RGB, оттенки серого и CMYK приводятся
к RGB, затем изображение переводится в палитру до 256 цветов.
GIF содержит один кадр; исходный JPEG не изменяется.
Ошибка чтения или неверный формат дают ненулевой код завершения.

`examples/demo.py` создаёт пять разных JPEG и запускает конвертер
отдельным процессом для каждого. Проверяются формат GIF и размеры.
Протокол находится в `examples/results.json`; сами изображения
создаются в `examples/generated` и не включаются в git.

`convert(source, destination)` выполняет преобразование и возвращает
размеры. `main()` в модуле `convert` обрабатывает аргументы CLI.
Тесты конвертера находятся в `tests/test_convert.py`.

## Этап 2. HTTP API и файловое хранение

```console
python -m jpeg_gif.server --backend file --data-dir data --port 8000
```

Сервер слушает `127.0.0.1`. Для каждого HTTP-запроса используется
`BaseHTTPRequestHandler` стандартной библиотеки. Задание сохраняется
со статусом `queued`, HTTP-ответ отправляется без ожидания конвертации.
Один фоновый поток запускает `python -m jpeg_gif.convert` через
`subprocess.run`. Состояния: `queued` → `running` → `done` или `failed`.
`enqueued` равен 1 до завершения и 0 после. Очередь восстанавливается
из незавершённых записей при перезапуске. `Ctrl+C` завершает уже
принятые задания до закрытия хранилища. Одновременно следует запускать
только один экземпляр сервера на одну папку данных.

Параметры `--host`, `--port`, `--data-dir`, `--backend`, `--test-mode`
задают адрес, порт, папку данных, слой хранения и тестовый режим.
По умолчанию это `127.0.0.1`, `8000`, `data`, SQLite через PonyORM,
реальное преобразование. В `--test-mode` subprocess не запускается:
ответ получает состояние `skipped`, пустые `response` и `error`.

### Маршруты таблицы 9

Все ответы, включая ошибки приложения, имеют формат JSON.
Успешные операции возвращают 200. Параметры передаются в строке
запроса; у двух маршрутов поиска родительский ключ находится в пути.
Тело запроса не используется.

| Метод | Маршрут | Параметры | Метод клиента |
|---|---|---|---|
| POST | `/api/add-individual` | поля Individual без key | `individual_add` |
| GET | `/api/dump-individual` | фильтры Individual | `individual_dump` |
| GET | `/api/retrieve-individual` | key | `individual_retrieve` |
| POST | `/api/add-assignment` | individual, payload | `assignment_add` |
| GET | `/api/dump-assignment/:individual` | фильтры Assignment | `assignment_dump` |
| GET | `/api/retrieve-assignment` | key | `assignment_retrieve` |
| GET | `/api/dump-response/:assignment` | фильтры Response | `response_dump` |
| GET | `/api/retrieve-response` | key | `response_retrieve` |
| GET | `/api/dump-report` | нет | `report_dump` |

Проверки обязательных заголовков выполняются в порядке задания:

1. Для POST, PUT, PATCH: `Content-Type: application/json`, иначе 415.
2. Для любого поддерживаемого метода: `Accept: application/json`, иначе 406.
3. Затем `Accept-Language: en`, иначе 406.

Неверные значения обрабатываются так же, как отсутствие заголовка.
Проверка заголовков предшествует разбору параметров и маршрута.
Неизвестный маршрут или ключ даёт 404, неверный параметр — 400.
Дублирующиеся параметры, неизвестные поля и ручное назначение key
отклоняются. Фильтры — точное равенство; без фильтров возвращается
полный список. Поиск в пределах отсутствующего родителя даёт `[]`.

### Данные

| Таблица | Поля по ER-диаграмме |
|---|---|
| Individual | key:int, timestamp:int, ip:str, locale:str, platform:str, user_agent:str |
| Assignment | key:int, timestamp:int, payload:str, individual:int, state:str, enqueued:int |
| Response | key:int, timestamp:int, response:str, state:str, error:str, assignment:int, cache_hit:int |

`key` — последовательный первичный ключ. `timestamp` — целые секунды
Unix UTC; при создании ставится сервером, для Individual/Assignment
может быть задан явно. Пропущенные строковые поля получают `""`.
Связи Assignment → Individual и Response → Assignment обязательны.
Состояние задания и признак очереди назначаются сервером.
`cache_hit` всегда 0: повторное задание преобразуется заново.

`payload` — строка с JSON `{"source":"photo.jpg"}`. Имя разрешается
относительно `data/inbox`; выход за пределы этой папки запрещён.
Файл заранее помещается в inbox на сервере. Это файловый сервис
с общей входной папкой: отдельного маршрута загрузки в таблице 9 нет.
Так изображения любого допустимого размера не помещаются в URL.
Формат файла проверяется при выполнении, а ошибка сохраняется
в Response. Тайм-аут одного запуска CLI — 60 секунд.

`response` — строка с JSON `{"file":"outbox/1.gif","gif":"..."}`,
где `gif` содержит Base64 готового файла. Клиент может получить
изображение через API, не имея доступа к выходной папке сервера.

Отчёт реализует формулу (9): сначала отбирает Response с
`timestamp >= now - 9*60`, затем правым внешним соединением
сопоставляет Assignment и оставляет `payload`, `error`, `response`.
Проекция устраняет дубликаты. Задания без ответа в отчёт не попадают;
при отсутствии соответствующего задания payload был бы null.
В обычном режиме такая ситуация исключена обязательной связью.

### Пример клиента

Сначала скопируйте JPEG в `data/inbox/photo.jpg`, затем выполните:

```python
import base64
import json
from pathlib import Path
import time

from jpeg_gif.client import ApiClient

api = ApiClient()
person = api.individual_add({
    "ip": "127.0.0.1", "locale": "en", "platform": "Windows",
    "user_agent": "coursework-client",
})
task = api.assignment_add({
    "individual": person["key"],
    "payload": json.dumps({"source": "photo.jpg"}),
})
deadline = time.monotonic() + 70
while not (answers := api.response_dump(task["key"])):
    if time.monotonic() >= deadline:
        raise TimeoutError("Conversion did not finish")
    time.sleep(0.1)
answer = answers[0]
if answer["state"] != "done":
    raise RuntimeError(answer["error"] or answer["state"])
result = json.loads(answer["response"])
Path("downloaded.gif").write_bytes(base64.b64decode(result["gif"]))
print(api.report_dump())
```

### Проверки второго этапа

```console
python -m coverage run -m pytest tests/test_mbt.py
python -m coverage report
python -m coverage html
```

В `tests/test_mbt.py` единственный тест создаётся из
`RuleBasedStateMachine`. Hypothesis генерирует строки, выбор родителей
и последовательности операций. Эталон — отдельные списки словарей.
Все девять маршрутов проверяются через реальный TCP и `ApiClient`.
Проверяются связи, поля, поиск, чтение, отчёт и ошибки заголовков.
Сценарии полностью изолированы временными папками и свободными портами.
Обычные тесты CLI не участвуют в отчёте покрытия HTTP.

### Состав модулей

- `schema`: типы ER-полей, преобразование целых и проверка параметров.
- `file_store`: `read`, `insert`, `update`, `close`; JSON с заменой файла.
- `model`: операции таблиц, `finish` для ответа и `report_dump` для отчёта.
- `jobs`: `input_file` проверяет путь, `Jobs.submit` ставит задание,
  `Jobs.close` дожидается очереди; внутренние методы исполняют CLI.
- `http_api`: `query_values` разбирает параметры, `Handler` проверяет
  заголовки, выбирает маршрут и формирует JSON, `AppServer` связывает
  HTTP с моделью и очередью.
- `client`: девять методов таблицы выше; `request` возвращает код
  и JSON без исключения по HTTP-статусу, остальные методы вызывают
  `ApiError` при ошибке. Настройки: host и port.
- `server`: `create_store` выбирает хранение, `main` запускает сервер.

Внутренние операции модели: `_dump` применяет фильтры, `_retrieve`
находит запись или сообщает 404. `new_record` подставляет значения
полей; `filters` проверяет названия и типы; `integer` разбирает целое.
`DomainError` переносит сообщение и код ошибки в HTTP-слой.
`FileStore._save` сохраняет данные через временный файл.
`_replace` повторяет атомарную замену при краткой блокировке файла
в Windows, не более десяти попыток с интервалом 0,05 секунды.
`Handler._handle` обрабатывает запрос, `_headers` проверяет заголовки,
`_dispatch` сопоставляет маршрут, `_invoke` вызывает операцию модели,
`_reply` отправляет JSON; `log_message` отключает стандартный журнал.
`ApiClient._call` превращает неуспешный HTTP-код в `ApiError`.
У очереди `_recover` восстанавливает задания, `_loop` читает очередь,
`_execute` сохраняет итог, `_convert` запускает CLI и кодирует GIF.
В примерах `run_example` проверяет отдельное изображение, а `main`
создаёт пять входов и протокол. Служебные функции тестов описаны
docstring в соответствующих файлах.

## Этап 3. SQLite и PonyORM

```console
run.bat --backend sqlite --data-dir data
```

Итоговая версия по умолчанию использует SQLite. `--backend file`
сохраняет возможность воспроизвести второй этап. Данные двух слоёв
независимы: `data/records.json` и `data/records.sqlite3`.
Автоматической миграции между ними нет.

`pony_store.define_entities` описывает Individual, Assignment, Response
из рисунка 9. Связи заданы через `Required`, обратные коллекции — `Set`.
`PonyStore` реализует `read`, `insert`, `update`, `close` через сущности
PonyORM и `db_session`, без строк SQL. После каждой операции закрывается
соединение текущего потока. Значения связей в API представлены целыми
ключами; внутренние коллекции ORM не включаются в JSON.
`_session` управляет транзакцией и соединением, `_record` превращает
сущность в словарь ER-полей, `_values` заменяет внешние ключи
ссылками на ORM-сущности. Для строк отключён `autostrip`, чтобы
файловый слой и SQLite одинаково сохраняли пробелы.

`Model` имеет необязательные часы `clock` для воспроизводимой проверки
границы отчёта; сервер использует текущее время.

### Повторение проверок обоих слоёв

В PowerShell из активированного окружения:

```powershell
$env:TEST_BACKEND = "file"
python -m coverage run --data-file=.coverage.file -m pytest tests/test_mbt.py tests/test_workflow.py
python -m coverage report --data-file=.coverage.file
$env:TEST_BACKEND = "sqlite"
python -m coverage run --data-file=.coverage.sqlite -m pytest tests/test_mbt.py tests/test_workflow.py
python -m coverage report --data-file=.coverage.sqlite
python -m coverage html --data-file=.coverage.sqlite
python -m pytest tests/test_convert.py
python -m pycodestyle --max-line-length=80 src tests examples tools
python tools/check_quality.py
```

В Linux переменная задаётся перед командой, например:
`TEST_BACKEND=sqlite python -m pytest tests/test_mbt.py`.
Скрипт `run.bat test` запускает весь набор тестов. Для воспроизводимого
отчёта именно по HTTP запускаются только `test_mbt.py` и
`test_workflow.py`: все их тестовые случаи генерирует Hypothesis.

`test_workflow.py` дополнительно проверяет настоящий subprocess,
асинхронность, формат и содержимое полученного GIF, неверные JPEG,
границу окна отчёта, устранение дубликатов проекции и восстановление
очереди. Стандартные модульные тесты конвертера не примешиваются
к отчётам покрытия API. HTML-отчёт создаётся в `htmlcov` и не входит
в git; текстовые результаты для сдачи находятся в `reports`.

`tools/check_quality.py` проверяет длину файлов, строк, функций, число
аргументов, комментарии вне docstring и сложность функций не выше 10.
Числа в сравнениях должны быть именованными константами; исключены
структурные 0 и 1. PEP8 отдельно проверяется `pycodestyle`.

## Сопоставление с критериями

| Требование | Реализация / подтверждение |
|---|---|
| Этап 1: файл → файл | `src/jpeg_gif/convert.py` |
| Пять примеров | `examples/demo.py`, `examples/results.json` |
| Этап 2: девять маршрутов | `http_api.ROUTES`, `tests/test_mbt.py` |
| JSON, заголовки и их порядок | `Handler`, правила `header_matrix`, `bad_queries` |
| subprocess и тестовый режим | `Jobs`, `test_workflow.py` |
| Клиент таблица_действие | `ApiClient`, девять методов |
| MBT через RuleBasedStateMachine | `ApiMachine` и независимые списки-эталоны |
| Покрытие ветвей API | `reports/coverage-file.txt`, `reports/coverage-sqlite.txt` |
| Этап 3: SQLite через PonyORM | `pony_store.py`, тот же набор MBT |
| История этапов | отдельные `feat(cli)`, `feat(api)`, `feat(storage)` |
| Структура репозитория | README, .gitignore, src, tests, run.bat |
| Ограничения оформления | `reports/quality.txt`, `tools/check_quality.py` |

## Ограничения

GIF имеет палитру до 256 цветов, поэтому оттенки JPEG могут измениться.
Получается одно кадровое изображение, а не анимация. Папка inbox
предназначена для заранее размещённых на сервере файлов; авторизации
в варианте 9 нет. Файлы и результаты автоматически не удаляются.
При аварии между записью ответа и обновлением задания восстановление
использует уже сохранённый ответ, не создавая второй. Гарантия очереди
при аварийном завершении — повторное выполнение незавершённой работы,
поэтому выходной файл имеет стабильное имя по ключу задания.

Этапы защищаются очно согласно общим условиям практической работы.
Репозиторий: https://github.com/mix1v/python_mirea

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
python -m pycodestyle --max-line-length=79 src tests examples tools
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

## Защита варианта 9 на компьютере преподавателя

Сервис принимает задание на преобразование JPEG в GIF и сразу возвращает
номер задания. Фоновый поток запускает конвертер, а клиент забирает результат
по номеру отдельным запросом. На этапе 2 записи хранятся в JSON, на этапе 3 —
в SQLite через PonyORM.

### Подготовка на Windows

1. Открой [репозиторий на GitHub](https://github.com/mix1v/python_mirea),
   выбери **Code → Download ZIP** и распакуй архив.
2. Открой в проводнике распакованную папку, где лежит `pyproject.toml`.
   Чтобы открыть CMD в этой папке, введи `cmd` в адресной строке и нажми Enter.
3. Проверь Python и установи проект с зависимостями. На защите удобно
   использовать Python 3.14: в нём есть встроенная команда для просмотра SQLite.
   Для первой установки зависимостей нужен интернет.

```bat
python --version
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Все команды ниже запускай из той же папки. Если понадобится второе окно CMD,
открой его таким же способом. Окружение `.venv` создаётся один раз.

### 1. Запустить конвертер первого этапа

```bat
.venv\Scripts\python.exe examples\demo.py
.venv\Scripts\python.exe -m jpeg_gif.convert examples\generated\red.jpg examples\generated\result.gif
explorer examples\generated
```

Первый запуск создаёт пять JPEG, прогоняет каждый через конвертер и проверяет
формат и размеры результата. В выводе у всех пяти примеров будет `"ok": true`.
Второй запуск показывает, как пользоваться самой утилитой. Открой `red.jpg`
и `result.gif` в проводнике. В [`convert.py`](src/jpeg_gif/convert.py)
покажи `main()` и `convert()`.

На защите можно сказать: «Первый аргумент — входной JPEG, второй — путь
для нового GIF. Конвертер читает исходник и сохраняет результат на диск».

### 2. Найти обработчик 4.1 второго этапа

В [`http_api.py`](src/jpeg_gif/http_api.py) найди `/api/dump-report` в `ROUTES`.
Это `GET /api/dump-report`. Покажи, как `_dispatch()` находит маршрут,
а `_invoke()` вызывает `Model.report_dump()` из [`model.py`](src/jpeg_gif/model.py).

На защите можно сказать: «Отчёт берёт ответы за последние девять минут,
находит данные связанных заданий и возвращает `payload`, `error` и `response`.
Одинаковые строки исключаются». Результат запроса можно показать сразу после
создания задания в следующем пункте.

### 3. Показать операцию 2.1 второго этапа

Покажи `assignment_add()` в [`client.py`](src/jpeg_gif/client.py), маршрут
`POST /api/add-assignment` в [`http_api.py`](src/jpeg_gif/http_api.py)
и методы `submit()` и `_convert()` в [`jobs.py`](src/jpeg_gif/jobs.py).
В `submit()` видно, как задание попадает в очередь, а в `_convert()` — как
через `subprocess.run()` запускается утилита первого этапа.

В первом окне CMD запусти файловый сервер и оставь окно открытым.

```bat
.venv\Scripts\python.exe -m jpeg_gif.server --backend file --data-dir data
```

Когда появится `API: http://127.0.0.1:8000`, открой второе окно CMD,
скопируй JPEG во входную папку сервера и запусти Python.

```bat
copy /Y examples\generated\red.jpg data\inbox\photo.jpg
.venv\Scripts\python.exe
```

В строке `>>>` вводи команды по очереди, без самого приглашения `>>>`.

```python
import json
from jpeg_gif.client import ApiClient
api = ApiClient()
person = api.individual_add({"platform": "Windows"})
payload = json.dumps({"source": "photo.jpg"})
task = api.assignment_add({"individual": person["key"], "payload": payload})
print(task)
print(api.response_dump(task["key"]))
```

В `task` будет статус `queued`. В ответе будет `done` и данные GIF.
Если список ответов пока пуст, повтори `print(api.response_dump(task["key"]))`.
Когда появится `done`, выполни `print(api.report_dump())`, чтобы показать
результат операции 4.1. Готовый GIF лежит в `data\outbox`, его имя совпадает
с номером задания. Выйди из Python командой `exit()` и останови сервер
клавишами **Ctrl+C** в первом окне.

На защите можно сказать: «Клиент получает номер сразу после принятия заявки.
Конвертация идёт в фоне, поэтому результат клиент запрашивает отдельно».

### 4. Показать MBT и контрпример

В [`tests/test_mbt.py`](tests/test_mbt.py) покажи класс `ApiMachine`,
правила `@rule` и сравнение ответа с эталоном в `add_assignment()`.
Тест сам запускает HTTP-сервер в тестовом режиме.

```bat
set "TEST_BACKEND=file"
.venv\Scripts\python.exe -m pytest tests/test_mbt.py -q
```

Исправный клиент даёт `1 passed`. Временно добавь в `assignment_add()`
в [`client.py`](src/jpeg_gif/client.py) одну строку перед `return` с тем же
отступом, что у `return`.

```python
        values = dict(values, payload='{"source": "wrong.jpg"}')
```

Сохрани файл и повтори команду `pytest` выше. Ожидается `1 failed`.
Покажи отличие в `payload` и сценарий, который Hypothesis выводит рядом
с ошибкой (`Failing test case` или `Falsifying example`). Затем удали
добавленную строку, сохрани файл и повтори тест до `1 passed`.

Этот дефект показывает ошибку при записи данных через HTTP-клиент.
В таблице варианта 9 операция 2.1 создаёт задание. Отдельного маршрута
для изменения существующего задания в этом варианте нет.

На защите можно сказать: «Клиент отправил подменённое имя JPEG. Эталон
ожидал исходное имя, и Hypothesis вывел короткий сценарий с расхождением».

### 5. Показать файл SQLite третьего этапа

В первом окне CMD запусти сервер с SQLite.

```bat
.venv\Scripts\python.exe -m jpeg_gif.server --backend sqlite --data-dir data
```

Во втором окне повтори команды клиента из пункта 3, чтобы в SQLite появились
Individual, Assignment и Response. Затем останови сервер через **Ctrl+C**.
Данные файлового этапа лежат в `data\records.json`, а данные третьего этапа —
в `data\records.sqlite3`. Покажи файл базы в проводнике.

```bat
explorer data
sqlite3 data\records.sqlite3
```

Внутри `sqlite3` выполни:

```sql
.tables
SELECT key, individual, state, enqueued FROM Assignment;
SELECT key, assignment, state FROM Response;
.quit
```

Если отдельной программы `sqlite3` нет, в Python 3.12 и новее есть встроенная
утилита. Выполни команды в CMD.

```bat
.venv\Scripts\python.exe -m sqlite3 data\records.sqlite3 "SELECT name FROM sqlite_master WHERE type='table';"
.venv\Scripts\python.exe -m sqlite3 data\records.sqlite3 "SELECT key, individual, state, enqueued FROM Assignment;"
.venv\Scripts\python.exe -m sqlite3 data\records.sqlite3 "SELECT key, assignment, state FROM Response;"
```

Покажи классы `Individual`, `Assignment`, `Response` в
[`pony_store.py`](src/jpeg_gif/pony_store.py). На защите можно сказать:
«PonyORM связывает классы Python с таблицами SQLite. При переключении на
SQLite клиент продолжает отправлять те же HTTP-запросы».

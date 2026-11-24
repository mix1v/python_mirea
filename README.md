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

Эта инструкция для **этапов 2 и 3**. Покажи, как клиент отправляет задание
на преобразование JPEG в GIF, получает номер, а затем забирает результат.
На этапе 2 записи хранятся в JSON. На этапе 3 те же запросы работают с SQLite.

### Подготовка на Windows

1. Открой [репозиторий](https://github.com/mix1v/python_mirea), нажми
   **Code → Download ZIP** и распакуй архив.
2. В проводнике открой папку, где лежат `pyproject.toml` и `README.md`.
   Введи `cmd` в адресной строке проводника и нажми Enter. Это **окно 1**.
3. Выполни команды ниже. Для установки нужен интернет. На репетиции
   использовался Python 3.14, команда `python --version` покажет версию на ПК.
   Если `python` не найден, для запуска на этом ПК понадобится установленный Python.

```bat
python --version
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Из той же папки открой **окно 2** таким же способом. В первом окне запускается
сервер, во втором выполняются запросы и тесты. Блоки Python вводи после
появления `>>>`. Блоки CMD вводи там, где строка заканчивается на `>`.
Сами символы приглашения копировать не нужно.

### Этап 2. Запустить сервер и показать 2.1 и 4.1

**Окно 1.** Запусти файловый сервер.

```bat
.venv\Scripts\python.exe -m jpeg_gif.server --backend file --data-dir data\defense-file --port 8000
```

Дождись `API: http://127.0.0.1:8000`. Оставь сервер работать. Он сам создаст
папки `inbox` и `outbox` в каталоге данных. Если в окне снова появилось
приглашение CMD, посмотри ошибку и запусти сервер заново. Если порт занят,
возьми `--port 8002` и ниже создай клиента через `ApiClient(port=8002)`.

**Окно 2.** Создай маленький JPEG сразу во входной папке и открой Python.
Этот JPEG нужен только как вход для проверки API.

```bat
.venv\Scripts\python.exe -c "from PIL import Image; Image.new('RGB', (64, 48), 'red').save('data/defense-file/inbox/photo.jpg')"
.venv\Scripts\python.exe
```

Когда увидишь `>>>`, выполни эти строки. Если сервер запущен на 8002,
замени `ApiClient()`, как указано выше.

```python
import json
from jpeg_gif.client import ApiClient
api = ApiClient()
person = api.individual_add({"platform": "Windows"})
payload = json.dumps({"source": "photo.jpg"})
task = api.assignment_add({"individual": person["key"], "payload": payload})
print(task["key"], task["state"])
```

Появятся номер и `queued`. Это результат **2.1**, запроса
`POST /api/add-assignment`. Если первая операция выдала `WinError 10061`,
проверь, что сервер всё ещё работает в окне 1 и что порты совпадают.
Затем повтори команды начиная с `person = ...`.

В том же Python проверь ответ.

```python
answers = api.response_dump(task["key"])
print([row["state"] for row in answers])
```

Если увидишь `[]`, повтори обе строки. Дождись `['done']`. При `failed` вызови
`print(answers[0]["error"])` и проверь, что JPEG лежит в `inbox` текущего сервера.

Теперь выполни запрос **4.1**, `GET /api/dump-report`. Чтобы не выводить длинную
строку с содержимым GIF, покажи поля отчёта и путь к файлу.

```python
report = api.report_dump()
print([(row["payload"], row["error"], json.loads(row["response"])["file"] if row["response"] else "") for row in report])
print(json.loads(answers[0]["response"])["file"])
exit()
```

В CMD открой `explorer data\defense-file\outbox` и покажи GIF с номером задания.
Записи этого запуска можно открыть командой `notepad data\defense-file\records.json`.
После показа останови сервер через **Ctrl+C в окне 1**.

| Что попросили показать | Где открыть код | Что сказать |
|---|---|---|
| **4.1 Отчёт** | В [http_api.py](src/jpeg_gif/http_api.py) найди `/api/dump-report` в `ROUTES`, затем `_dispatch()` и `_invoke()`. В [model.py](src/jpeg_gif/model.py) открой `report_dump()`. | Отчёт выбирает ответы за последние девять минут, находит задание для каждого и возвращает `payload`, `error` и `response`. Одинаковые строки убираются. |
| **2.1 Создание задания** | В [http_api.py](src/jpeg_gif/http_api.py) найди `/api/add-assignment` и ветку `assignment_add` в `_invoke()`. В [jobs.py](src/jpeg_gif/jobs.py) покажи `submit()`, затем `subprocess.run()` в `_convert()`. | `submit()` сохраняет задание и кладёт его в очередь. Клиент сразу получает номер и `queued`. Рабочий поток запускает конвертер отдельно, а клиент потом запрашивает ответ. |

**Если спросят, какие данные передаются.** `Individual` — запись клиента,
`Assignment` — его задание, `Response` — результат. В 2.1 клиент передаёт
номер `Individual` и `payload` с именем входного файла. В ответе конвертера
GIF записан на диск и представлен строкой Base64, чтобы его можно было передать
в JSON. Методы `ApiClient` сами добавляют нужные HTTP-заголовки.

### Этап 2. Показать MBT и контрпример

В **окне 2**, уже в CMD, запусти тест с файловым хранилищем.

```bat
set "TEST_BACKEND=file"
.venv\Scripts\python.exe -m pytest tests/test_mbt.py -q
```

Ожидается `1 passed`. Тест поднимает отдельный сервер и использует временные
данные. Открой [tests/test_mbt.py](tests/test_mbt.py) и покажи класс `ApiMachine`,
правила `@rule`, проверку `check_lists()` и `assert without_time(row) == expected`
в `add_assignment()`.

> MBT — модельное тестирование. Hypothesis подбирает данные и последовательности
> действий. Тест сам хранит ожидаемые записи и сравнивает их с ответами API.

Затем открой [client.py](src/jpeg_gif/client.py), найди
`def assignment_add(self, values):` и **временно** добавь перед `return`
строку с тем же отступом.

```python
        values = dict(values, payload='{"source": "wrong.jpg"}')
```

Сохрани файл и повтори ту же команду `pytest`. Ожидается `1 failed`.
Найди разницу в `payload` и блок `Failing test case` или `Falsifying example`.

> Клиент отправил `wrong.jpg` вместо исходного имени. Сервер принял другие
> данные, и проверка обнаружила расхождение с эталоном. Hypothesis показал
> короткий сценарий, на котором ошибка повторяется.

В общей памятке упомянут метод обновления данных. Для варианта 9 в таблице
маршрутов есть создание задания **2.1**, поэтому подмена показана в его клиентском
методе. **Удали добавленную строку**, сохрани и повтори тест до `1 passed`.

### Этап 3. Записать задание в SQLite и показать базу

**Окно 1.** Убедись, что файловый сервер остановлен. Запусти SQLite.

```bat
.venv\Scripts\python.exe -m jpeg_gif.server --backend sqlite --data-dir data\defense-sqlite --port 8000
```

Если ранее выбрал порт 8002, используй его и здесь. Дождись строки `API: ...`.
**Окно 2.** Создай входной JPEG в каталоге этого запуска.

```bat
.venv\Scripts\python.exe -c "from PIL import Image; Image.new('RGB', (64, 48), 'red').save('data/defense-sqlite/inbox/photo.jpg')"
.venv\Scripts\python.exe
```

Повтори Python-блок от `import json` до `print(task["key"], task["state"])`
из этапа 2. Дождись `['done']` с помощью двух строк `answers = ...` и
`print([row["state"] for row in answers])`. Запомни номер задания. Выйди из Python
командой `exit()`. Останови сервер в окне 1 через **Ctrl+C**.

В CMD открой папку с базой и выведи её содержимое. Команды с `-m sqlite3`
доступны в Python 3.12 и новее и работают при отсутствии отдельного `sqlite3.exe`.

```bat
explorer data\defense-sqlite
.venv\Scripts\python.exe -m sqlite3 data\defense-sqlite\records.sqlite3 "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
.venv\Scripts\python.exe -m sqlite3 data\defense-sqlite\records.sqlite3 "SELECT key, individual, state, enqueued FROM Assignment ORDER BY key DESC LIMIT 1;"
.venv\Scripts\python.exe -m sqlite3 data\defense-sqlite\records.sqlite3 "SELECT key, assignment, state FROM Response ORDER BY key DESC LIMIT 1;"
```

Покажи файл `records.sqlite3` и три таблицы. У последнего задания должен быть
твой номер, статус `done` и `enqueued = 0`. В последнем ответе поле `assignment`
указывает на тот же номер.

Если установлен отдельный SQLite CLI, можно выполнить
`sqlite3 data\defense-sqlite\records.sqlite3`, затем `.tables`, те же SQL-запросы
и `.quit` в его приглашении. Если отдельного CLI нет и версия Python ниже 3.12, список заданий можно вывести стандартной библиотекой.

```bat
.venv\Scripts\python.exe -c "import sqlite3; db=sqlite3.connect('data/defense-sqlite/records.sqlite3'); print(db.execute('SELECT key, individual, state FROM Assignment ORDER BY key DESC LIMIT 1').fetchall()); db.close()"
```

В [server.py](src/jpeg_gif/server.py) покажи `create_store()`, где переключается
хранилище. В [pony_store.py](src/jpeg_gif/pony_store.py) покажи `define_entities()`
с тремя классами и `_session()`, где открывается `db_session`.

> PonyORM связывает классы Python с таблицами SQLite. Маршруты, очередь и клиент
> работают по-прежнему, потому что модель использует одинаковые операции хранения.

Для проверки с SQLite используй тот же MBT. Изменение клиента из этапа 2 должно
быть уже убрано.

```bat
set "TEST_BACKEND=sqlite"
.venv\Scripts\python.exe -m pytest tests/test_mbt.py -q
```

Ожидается `1 passed`. Если попросят показать покрытие ветвей, открой готовые
отчёты [для файлового слоя](reports/coverage-file.txt) и
[для SQLite](reports/coverage-sqlite.txt). В строке `http_api.py` указано
100% покрытия в обоих отчётах. Строка `TOTAL` показывает покрытие всего проекта.

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

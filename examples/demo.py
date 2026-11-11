"""Создать пять JPEG, вызвать CLI и проверить полученные файлы GIF."""

import json
from pathlib import Path
import subprocess
import sys

from PIL import Image


CASES = [
    ("red", "RGB", (64, 48), "red"),
    ("gray", "L", (73, 51), 128),
    ("wide", "RGB", (240, 40), "navy"),
    ("single", "RGB", (1, 1), "white"),
    ("cmyk", "CMYK", (90, 120), (0, 180, 80, 0)),
]


def run_example(case, folder):
    """Проверить формат и размеры результата одного запуска CLI."""
    name, mode, size, color = case
    source = folder / f"{name}.jpg"
    output = folder / f"{name}.gif"
    Image.new(mode, size, color).save(source, "JPEG")
    subprocess.run(
        [sys.executable, "-m", "jpeg_gif.convert", str(source), str(output)],
        check=True,
    )
    with Image.open(output) as result:
        assert result.format == "GIF"
        assert result.size == size
    return {"name": name, "input_mode": mode, "size": size, "ok": True}


def main():
    """Сохранить воспроизводимые примеры и текстовый протокол проверки."""
    folder = Path(__file__).parent / "generated"
    folder.mkdir(exist_ok=True)
    results = [run_example(case, folder) for case in CASES]
    report = json.dumps(results, indent=2)
    (folder.parent / "results.json").write_text(report + "\n", "utf-8")
    print(report)


if __name__ == "__main__":
    main()

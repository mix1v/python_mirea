"""Файловый конвертер JPEG в GIF, запускаемый отдельно от сервера."""

import argparse
from pathlib import Path

from PIL import Image, ImageOps


def convert(source, destination):
    """Проверить формат, учесть EXIF-поворот и сохранить GIF на диск."""
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output must be different files")
    with Image.open(source) as image:
        if image.format != "JPEG":
            raise ValueError("Input must be a JPEG image")
        oriented = ImageOps.exif_transpose(image).convert("RGB")
        palette = oriented.quantize(colors=256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        palette.save(destination, format="GIF")
        return {"width": oriented.width, "height": oriented.height}


def main():
    """Принять имена входного JPEG и выходного GIF из командной строки."""
    parser = argparse.ArgumentParser(description="Convert JPEG to GIF")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        convert(args.input, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Conversion failed: {error}\n")


if __name__ == "__main__":
    main()

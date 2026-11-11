"""Проверки файлового преобразования отдельно от покрытия HTTP API."""

from PIL import Image
import pytest

from jpeg_gif.convert import convert


@pytest.mark.parametrize("mode", ["RGB", "L", "CMYK"])
def test_conversion(tmp_path, mode):
    """Цветовые режимы JPEG сохраняют размеры после конвертации."""
    source = tmp_path / "input.jpg"
    target = tmp_path / "nested" / "output.gif"
    Image.new(mode, (17, 29)).save(source, "JPEG")
    assert convert(source, target) == {"width": 17, "height": 29}
    with Image.open(target) as image:
        assert image.format == "GIF"
        assert image.size == (17, 29)


def test_wrong_format(tmp_path):
    """Расширение jpg само по себе не делает PNG изображением JPEG."""
    source = tmp_path / "false.jpg"
    Image.new("RGB", (2, 2)).save(source, "PNG")
    with pytest.raises(ValueError, match="JPEG"):
        convert(source, tmp_path / "output.gif")


def test_same_file(tmp_path):
    """Исходник нельзя перезаписать результатом."""
    source = tmp_path / "source.jpg"
    with pytest.raises(ValueError, match="different"):
        convert(source, source)

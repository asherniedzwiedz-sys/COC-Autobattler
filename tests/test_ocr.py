import numpy as np
import pytest

from cocbot import ocr
from tests.conftest import draw_text

needs_tesseract = pytest.mark.skipif(not ocr.available(), reason="tesseract not installed")


@pytest.mark.parametrize("text,expected", [
    ("1 234 567", 1234567), ("1,234,567", 1234567), ("1.234.567\n", 1234567),
    ("  42 ", 42), ("", None), ("abc", None),
])
def test_parse_int(text, expected):
    assert ocr.parse_int(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Max: 24 000 000", 24_000_000), ("max:12000000", 12_000_000), ("12 000 000", 12_000_000), ("Max:", None),
])
def test_parse_max(text, expected):
    assert ocr.parse_max(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Town Hall (Level 18)", 18), ("Town Hall (level 9)", 9), ("Lvl 5", 5), ("Town Hall", None),
])
def test_parse_level(text, expected):
    assert ocr.parse_level(text) == expected


def test_parse_fraction():
    assert ocr.parse_fraction("2/6") == (2, 6)
    assert ocr.parse_fraction("Builders 0 / 5") == (0, 5)
    assert ocr.parse_fraction("5") is None


def test_binarize_makes_text_black_on_white():
    img = np.full((40, 200, 3), (40, 80, 120), np.uint8)
    draw_text(img, "123", 10, 30)
    out = ocr.binarize(img)
    assert out.dtype == np.uint8 and set(np.unique(out)) <= {0, 255}
    assert (out == 255).mean() > 0.5


@needs_tesseract
def test_read_number_from_outlined_text():
    img = np.full((50, 260, 3), (30, 70, 110), np.uint8)
    draw_text(img, "1 234 567", 8, 36)
    assert ocr.read_number(img) == 1234567


def test_group_lines():
    from cocbot.vision import Box
    words = [ocr.Word("Cannon", Box(10, 100, 50, 12), 90), ocr.Word("Wall", Box(10, 50, 30, 12), 90),
             ocr.Word("x3", Box(50, 52, 15, 12), 90)]
    lines = ocr.group_lines(words)
    assert [ocr.line_text(line) for line in lines] == ["Wall x3", "Cannon"]
    assert ocr.line_box(lines[0]) == Box(10, 50, 55, 14)

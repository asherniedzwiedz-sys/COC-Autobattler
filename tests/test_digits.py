import cv2
import numpy as np
import pytest

from cocbot.digits import DigitReader, glyph_boxes
from cocbot.ocr import binarize
from tests.conftest import draw_text


def strip(text, scale=0.9, width=None):
    width = width or 40 + 26 * len(text)
    img = np.full((50, width, 3), (40, 70, 110), np.uint8)
    draw_text(img, text, 10, 38, scale=scale)
    return img


@pytest.fixture
def reader(tmp_path):
    r = DigitReader(tmp_path / "digits")
    r.save_glyphs(strip("0123456789"), "0123456789")
    r.save_glyphs(strip("1/2"), "1/2")
    return r


def test_ready_and_reads_numbers(reader):
    assert reader.ready()
    assert reader.read(strip("1 234 567")) == "1234567"
    assert reader.read(strip("90 805")) == "90805"
    assert reader.read(strip("3/6")) == "3/6"


def test_reads_other_sizes(reader):
    assert reader.read(strip("4 096", scale=1.3, width=200)) == "4096"


def test_unknown_glyph_fails_the_whole_read(reader):
    assert reader.read(strip("12A4")) is None


def test_background_blob_at_the_edge_is_ignored(reader):
    img = np.full((50, 320, 3), (40, 70, 110), np.uint8)
    draw_text(img, "5 678", 150, 38, scale=0.9)
    # a wedge-shaped highlight away from the number, like the one seen on a real screen
    cv2.fillPoly(img, [np.array([[6, 25], [44, 14], [44, 36]], np.int32)], (255, 255, 255))
    assert reader.read(img) == "5678"


def test_ambiguous_blob_fails_safe(reader):
    img = np.full((50, 320, 3), (40, 70, 110), np.uint8)
    draw_text(img, "5 678", 150, 38, scale=0.9)
    cv2.circle(img, (22, 25), 9, (255, 255, 255), 3)  # a ring could be a zero: don't guess
    assert reader.read(img) is None


def test_save_glyphs_checks_the_count(tmp_path):
    with pytest.raises(ValueError):
        DigitReader(tmp_path).save_glyphs(strip("123"), "12")
    with pytest.raises(ValueError):
        DigitReader(tmp_path).save_glyphs(strip("1A"), "1A")


def test_glyph_boxes_left_to_right():
    boxes = glyph_boxes(binarize(strip("7 1")))
    assert len(boxes) == 2 and boxes[0].x < boxes[1].x

import cv2
import numpy as np

from cocbot.vision import Box, Vision, is_price_red, resolve_region
from tests.conftest import draw_text, make_icon, make_screen, paste


def test_find_locates_template(vision):
    screen = paste(make_screen(), make_icon("gold"), 500, 300)
    m = vision.find(screen, "res_gold")
    assert m is not None and (m.box.x, m.box.y) == (500, 300)
    assert m.center == (518, 318)


def test_find_none_when_absent(vision):
    assert vision.find(make_screen(), "res_gold") is None


def test_find_all_and_region(vision):
    screen = make_screen()
    for x in (100, 400, 900):
        paste(screen, make_icon("gem"), x, 200)
    assert len(vision.find_all(screen, "res_gem")) == 3
    only_left = vision.find_all(screen, "res_gem", region=Box(0, 0, 600, 720))
    assert sorted(m.box.x for m in only_left) == [100, 400]


def test_icons_do_not_cross_match(vision):
    screen = make_screen()
    for i, kind in enumerate(("gold", "elixir", "dark", "close", "trap", "shop", "builder")):
        paste(screen, make_icon(kind), 60 + i * 150, 300)
    assert vision.find_all(screen, "res_gem", threshold=0.72) == []


def test_variants(template_dir):
    cv2.imwrite(str(template_dir / "res_gold__2.png"), make_icon("elixir"))
    vision = Vision(template_dir)
    screen = paste(make_screen(), make_icon("elixir"), 50, 50)
    assert vision.find(screen, "res_gold") is not None
    assert "res_gold" in vision.names_with_prefix("res_")


def test_box_relative_and_clip():
    icon = Box(100, 100, 20, 10)
    assert icon.relative(-2, 0, 0, 1) == Box(60, 100, 40, 10)
    assert Box(-5, -5, 20, 20).clip(10, 10) == Box(0, 0, 10, 10)
    assert Box(50, 50, 5, 5).clip(10, 10) is None


def test_resolve_region(vision):
    screen = paste(make_screen(), make_icon("builder"), 600, 10)
    assert resolve_region(("screen", 0.5, 0.5, 1.0, 1.0), screen, vision) == Box(640, 360, 640, 360)
    assert resolve_region(("icon", "builder_icon", 1, 0, 3, 1), screen, vision) == Box(636, 10, 72, 36)
    assert resolve_region(("icon", "res_gem", 1, 0, 3, 1), screen, vision) is None


def test_is_price_red():
    screen = np.full((100, 300, 3), 60, np.uint8)
    icon = Box(200, 30, 30, 30)
    draw_text(screen, "500000", 90, 55, colour=(255, 255, 255))
    assert not is_price_red(screen, icon)
    screen[:] = 60
    draw_text(screen, "500000", 90, 55, colour=(40, 40, 230))
    assert is_price_red(screen, icon)

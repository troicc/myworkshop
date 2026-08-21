from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.brand import load_brand
from app.models import SlidePlan, VisualBrief
from app.providers.image import MockImageProvider
from app.render import Renderer, resolve_font, wrap_title_text


def test_renderer_outputs_expected_canvas(tmp_path: Path) -> None:
    brand = load_brand(Path("brand/default/brand.yaml"))
    slide = SlidePlan(
        index=1,
        kind="cover",
        headline="早八来不及做饭｜8套10分钟早餐",
        subheadline="不用每天重新想，照着轮换就行",
        body_points=["燕麦香蕉杯", "鸡蛋全麦吐司", "酸奶水果碗"],
        visual=VisualBrief(primary_subject="三种早餐", exact_count=3),
    )
    raw = tmp_path / "raw.png"
    MockImageProvider("512x768").generate(
        prompt="renderer test",
        output_path=raw,
        visual=slide.visual,
        brand=brand,
        reference_paths=[],
    )
    output = tmp_path / "output.png"
    Renderer(brand).render_slide(
        slide=slide,
        output_path=output,
        total_slides=4,
        raw_image_path=raw,
    )
    with Image.open(output) as image:
        assert image.size == (1080, 1440)
        assert image.mode == "RGB"


def test_title_wrapper_preserves_semantic_halves() -> None:
    image = Image.new("RGB", (1080, 1440), "white")
    draw = ImageDraw.Draw(image)
    font = resolve_font(76, bold=True)
    lines = wrap_title_text(
        draw,
        "早八来不及做饭｜8套10分钟早餐",
        font,
        max_width=936,
        max_lines=3,
    )
    assert lines == ["早八来不及做饭", "8套10分钟早餐"]
    assert all("10分" not in line or "分钟" in line for line in lines)

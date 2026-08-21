from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Iterable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.brand import BrandSpec
from app.models import SlidePlan


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _candidate_font_paths(bold: bool) -> list[Path]:
    linux = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    )
    paths = [
        Path(linux),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    return paths


def resolve_font(size: int, *, bold: bool = False, extra_candidates: Iterable[str] = ()) -> ImageFont.FreeTypeFont:
    candidates = [Path(value).expanduser() for value in extra_candidates if value]
    candidates.extend(_candidate_font_paths(bold))
    for path in candidates:
        if not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size=size, index=0)
        except OSError:
            continue
    return ImageFont.load_default(size=size)  # type: ignore[return-value]


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text or " ", font=font)
    return box[2] - box[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    text = " ".join(text.replace("\n", " ").split())
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and text_width(draw, candidate, font) > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    if len(lines) < max_lines and current:
        lines.append(current.rstrip())
    consumed = "".join(lines).replace(" ", "")
    original = text.replace(" ", "")
    if consumed != original and lines:
        suffix = "…"
        last = lines[-1]
        while last and text_width(draw, last + suffix, font) > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip("，。；：、 ") + suffix
    return lines


def wrap_title_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    """Prefer semantic title breaks before falling back to character wrapping.

    A vertical-bar title such as ``场景｜数字化方案`` is part of the account's
    title grammar. Keeping both sides intact avoids broken units such as
    ``10分 / 钟`` and makes repeated covers visually recognisable.
    """
    normalized = " ".join(text.replace("\n", " ").split())
    parts = [part.strip() for part in re.split(r"[｜|]", normalized) if part.strip()]
    if 1 < len(parts) <= max_lines and all(
        text_width(draw, part, font) <= max_width for part in parts
    ):
        return parts
    return wrap_text(draw, normalized, font, max_width, max_lines)


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_gap: int,
) -> int:
    x, y = xy
    ascent, descent = font.getmetrics() if hasattr(font, "getmetrics") else (font.size, 0)
    height = ascent + descent
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += height + line_gap
    return y


def rounded_image(source: Image.Image, size: tuple[int, int], radius: int) -> Image.Image:
    fitted = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    fitted.putalpha(mask)
    return fitted


class Renderer:
    def __init__(self, brand: BrandSpec):
        self.brand = brand
        self.width = brand.canvas.width
        self.height = brand.canvas.height
        self.paper = hex_rgb(brand.palette.paper)
        self.ink = hex_rgb(brand.palette.ink)
        self.muted = hex_rgb(brand.palette.muted)
        self.primary = hex_rgb(brand.palette.primary)
        self.accent = hex_rgb(brand.palette.accent)
        self.card = hex_rgb(brand.palette.card)
        self.line = hex_rgb(brand.palette.line)
        sans = brand.typography.sans_candidates
        self.font_title = resolve_font(brand.typography.title_size, bold=True, extra_candidates=sans)
        self.font_h2 = resolve_font(brand.typography.h2_size, bold=True, extra_candidates=sans)
        self.font_body = resolve_font(brand.typography.body_size, extra_candidates=sans)
        self.font_body_bold = resolve_font(brand.typography.body_size, bold=True, extra_candidates=sans)
        self.font_small = resolve_font(brand.typography.small_size, extra_candidates=sans)
        self.font_small_bold = resolve_font(
            brand.typography.small_size, bold=True, extra_candidates=sans
        )

    def render_slide(
        self,
        *,
        slide: SlidePlan,
        output_path: Path,
        total_slides: int,
        raw_image_path: Path | None,
    ) -> None:
        image = self._paper_canvas(slide.headline)
        draw = ImageDraw.Draw(image)
        if slide.kind == "cover":
            self._render_cover(image, draw, slide, total_slides, raw_image_path)
        elif slide.kind == "cards":
            self._render_cards(image, draw, slide, total_slides, raw_image_path)
        elif slide.kind in {"steps", "checklist"}:
            self._render_steps(image, draw, slide, total_slides, raw_image_path)
        else:
            self._render_sources(image, draw, slide, total_slides)
        self._footer(draw)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output_path, format="PNG", optimize=True)

    def _paper_canvas(self, seed_text: str) -> Image.Image:
        image = Image.new("RGB", (self.width, self.height), self.paper)
        draw = ImageDraw.Draw(image, "RGBA")
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)
        for _ in range(1500):
            x = rng.randrange(self.width)
            y = rng.randrange(self.height)
            value = rng.choice((-1, 1)) * rng.randint(2, 8)
            color = tuple(max(0, min(255, channel + value)) for channel in self.paper)
            draw.point((x, y), fill=(*color, rng.randint(12, 30)))
        # Repeated editorial signature: corner disc + botanical curve.
        disc = int(self.width * 0.18)
        draw.ellipse(
            (self.width - disc, -disc // 2, self.width + disc // 3, disc),
            fill=(*self.accent, 235),
        )
        draw.arc(
            (-80, int(self.height * 0.63), int(self.width * 0.32), self.height + 80),
            260,
            70,
            fill=(*self.primary, 220),
            width=6,
        )
        return image

    def _header(self, draw: ImageDraw.ImageDraw, slide: SlidePlan, total: int) -> int:
        margin = self.brand.canvas.safe_margin
        pill_w = 230
        pill_h = 52
        draw.rounded_rectangle(
            (margin, 48, margin + pill_w, 48 + pill_h),
            radius=pill_h // 2,
            fill=self.primary,
        )
        draw.text(
            (margin + 22, 58),
            self.brand.copywriting.account_name,
            font=self.font_small_bold,
            fill=self.card,
        )
        page_text = f"#{slide.index:03d} · {slide.index}/{total}"
        draw.text(
            (self.width - margin - text_width(draw, page_text, self.font_small), 62),
            page_text,
            font=self.font_small,
            fill=self.muted,
        )
        return 130

    def _draw_title(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        y: int,
        max_width: int,
        max_lines: int,
        base_size: int | None = None,
    ) -> int:
        size = base_size or self.brand.typography.title_size
        margin = self.brand.canvas.safe_margin
        while size >= 42:
            font = resolve_font(
                size, bold=True, extra_candidates=self.brand.typography.sans_candidates
            )
            lines = wrap_title_text(draw, text, font, max_width, max_lines)
            metrics = font.getmetrics()
            total_h = len(lines) * (metrics[0] + metrics[1] + 8)
            if total_h <= (max_lines * (size + 18)):
                break
            size -= 4
        y2 = draw_lines(draw, lines, (margin, y), font, self.ink, 8)
        draw.rounded_rectangle(
            (margin, y2 + 4, margin + 250, y2 + 15),
            radius=6,
            fill=self.primary,
        )
        draw.ellipse((margin + 268, y2, margin + 290, y2 + 22), fill=self.accent)
        return y2 + 32

    def _render_cover(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        slide: SlidePlan,
        total: int,
        raw_path: Path | None,
    ) -> None:
        margin = self.brand.canvas.safe_margin
        y = self._header(draw, slide, total)
        y = self._draw_title(
            draw,
            slide.headline,
            y=y,
            max_width=self.width - 2 * margin,
            max_lines=self.brand.layout.title_max_lines,
        )
        subtitle_lines = wrap_text(
            draw,
            slide.subheadline or self.brand.copywriting.tagline,
            self.font_body,
            self.width - 2 * margin,
            2,
        )
        y = draw_lines(draw, subtitle_lines, (margin, y + 4), self.font_body, self.muted, 6) + 18
        visual_top = max(y, 400)
        visual_h = 580
        self._paste_visual(image, raw_path, (margin, visual_top, self.width - margin, visual_top + visual_h))
        label_y = visual_top + 24
        draw.rounded_rectangle(
            (margin + 24, label_y, margin + 196, label_y + 54),
            radius=27,
            fill=(*self.paper, 240),
        )
        draw.text(
            (margin + 46, label_y + 11),
            "本期解决",
            font=self.font_small_bold,
            fill=self.primary,
        )
        cards_top = visual_top + visual_h + 34
        points = slide.body_points[:3]
        if not points:
            points = ["明确场景", "给出方案", "保存执行"]
        gap = self.brand.layout.card_gap
        card_w = (self.width - 2 * margin - 2 * gap) // 3
        card_h = 205
        for index, point in enumerate(points):
            x = margin + index * (card_w + gap)
            self._mini_card(draw, (x, cards_top, x + card_w, cards_top + card_h), index + 1, point)

    def _render_cards(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        slide: SlidePlan,
        total: int,
        raw_path: Path | None,
    ) -> None:
        margin = self.brand.canvas.safe_margin
        y = self._header(draw, slide, total)
        y = self._draw_title(draw, slide.headline, y=y, max_width=830, max_lines=2, base_size=60)
        if slide.subheadline:
            y = draw_lines(
                draw,
                wrap_text(draw, slide.subheadline, self.font_body, 900, 2),
                (margin, y),
                self.font_body,
                self.muted,
                4,
            ) + 14
        visual_h = 500
        self._paste_visual(image, raw_path, (margin, y, self.width - margin, y + visual_h))
        list_top = y + visual_h + 28
        points = slide.body_points[:6]
        columns = 2
        gap = 18
        card_w = (self.width - 2 * margin - gap) // columns
        card_h = 142 if len(points) > 4 else 165
        for index, point in enumerate(points):
            row, col = divmod(index, columns)
            x = margin + col * (card_w + gap)
            top = list_top + row * (card_h + gap)
            if top + card_h > self.height - self.brand.layout.footer_height - 20:
                break
            self._numbered_point_card(draw, (x, top, x + card_w, top + card_h), index + 1, point)

    def _render_steps(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        slide: SlidePlan,
        total: int,
        raw_path: Path | None,
    ) -> None:
        margin = self.brand.canvas.safe_margin
        y = self._header(draw, slide, total)
        y = self._draw_title(draw, slide.headline, y=y, max_width=850, max_lines=2, base_size=58)
        visual_h = 450
        self._paste_visual(image, raw_path, (margin, y, self.width - margin, y + visual_h))
        panel_top = y + visual_h + 28
        panel_bottom = self.height - self.brand.layout.footer_height - 28
        draw.rounded_rectangle(
            (margin, panel_top, self.width - margin, panel_bottom),
            radius=self.brand.canvas.corner_radius,
            fill=self.card,
            outline=self.line,
            width=2,
        )
        points = slide.body_points[:6]
        available = panel_bottom - panel_top - 48
        row_h = max(82, available // max(1, len(points)))
        for index, point in enumerate(points):
            top = panel_top + 24 + index * row_h
            if top + 60 > panel_bottom:
                break
            circle = (margin + 26, top + 4, margin + 78, top + 56)
            draw.ellipse(circle, fill=self.accent if slide.kind == "steps" else self.primary)
            marker = str(index + 1) if slide.kind == "steps" else "✓"
            marker_w = text_width(draw, marker, self.font_small_bold)
            draw.text(
                (margin + 52 - marker_w // 2, top + 13),
                marker,
                font=self.font_small_bold,
                fill=self.card,
            )
            lines = wrap_text(draw, point, self.font_body, self.width - 2 * margin - 130, 2)
            draw_lines(draw, lines, (margin + 102, top), self.font_body, self.ink, 4)
            if index < len(points) - 1:
                draw.line(
                    (margin + 102, top + row_h - 12, self.width - margin - 28, top + row_h - 12),
                    fill=(*self.line, 120),
                    width=1,
                )

    def _render_sources(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        slide: SlidePlan,
        total: int,
    ) -> None:
        margin = self.brand.canvas.safe_margin
        y = self._header(draw, slide, total)
        y = self._draw_title(draw, slide.headline, y=y, max_width=850, max_lines=2, base_size=58)
        if slide.subheadline:
            y = draw_lines(
                draw,
                wrap_text(draw, slide.subheadline, self.font_body, 900, 2),
                (margin, y),
                self.font_body,
                self.muted,
                4,
            ) + 24
        panel_bottom = self.height - self.brand.layout.footer_height - 34
        draw.rounded_rectangle(
            (margin, y, self.width - margin, panel_bottom),
            radius=self.brand.canvas.corner_radius,
            fill=self.card,
            outline=self.line,
            width=2,
        )
        cursor_y = y + 34
        for index, point in enumerate(slide.body_points[:8], start=1):
            badge = f"{index:02d}"
            draw.rounded_rectangle(
                (margin + 28, cursor_y, margin + 92, cursor_y + 42),
                radius=21,
                fill=self.primary,
            )
            draw.text(
                (margin + 43, cursor_y + 8),
                badge,
                font=self.font_small_bold,
                fill=self.card,
            )
            lines = wrap_text(draw, point, self.font_body, self.width - 2 * margin - 160, 3)
            next_y = draw_lines(
                draw, lines, (margin + 116, cursor_y - 1), self.font_body, self.ink, 5
            )
            cursor_y = max(cursor_y + 70, next_y + 24)
            if cursor_y > panel_bottom - 90:
                break
        disclosure = self.brand.copywriting.ai_disclosure
        draw.rounded_rectangle(
            (margin + 28, panel_bottom - 90, self.width - margin - 28, panel_bottom - 28),
            radius=20,
            fill=(*self.paper, 255),
        )
        draw.text(
            (margin + 50, panel_bottom - 73),
            disclosure,
            font=self.font_small,
            fill=self.muted,
        )

    def _paste_visual(
        self,
        canvas: Image.Image,
        raw_path: Path | None,
        box: tuple[int, int, int, int],
    ) -> None:
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        if raw_path and raw_path.exists():
            with Image.open(raw_path) as source:
                visual = rounded_image(source, (width, height), self.brand.layout.image_radius)
        else:
            placeholder = Image.new("RGB", (width, height), self.card)
            placeholder_draw = ImageDraw.Draw(placeholder, "RGBA")
            placeholder_draw.ellipse(
                (width * 0.20, height * 0.25, width * 0.80, height * 0.88),
                fill=(*self.primary, 60),
            )
            visual = rounded_image(placeholder, (width, height), self.brand.layout.image_radius)
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (left + 14, top + 18, right + 14, bottom + 18),
            radius=self.brand.layout.image_radius,
            fill=(46, 35, 24, 45),
        )
        canvas.paste(shadow, (0, 0), shadow)
        canvas.paste(visual, (left, top), visual)
        ImageDraw.Draw(canvas).rounded_rectangle(
            box,
            radius=self.brand.layout.image_radius,
            outline=self.card,
            width=4,
        )

    def _mini_card(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        index: int,
        text: str,
    ) -> None:
        left, top, right, bottom = box
        draw.rounded_rectangle(box, radius=24, fill=self.card, outline=self.line, width=2)
        draw.ellipse((left + 18, top + 18, left + 58, top + 58), fill=self.accent)
        marker = str(index)
        marker_w = text_width(draw, marker, self.font_small_bold)
        draw.text(
            (left + 38 - marker_w // 2, top + 25),
            marker,
            font=self.font_small_bold,
            fill=self.card,
        )
        lines = wrap_text(draw, text, self.font_body_bold, right - left - 36, 3)
        draw_lines(draw, lines, (left + 18, top + 76), self.font_body_bold, self.ink, 4)

    def _numbered_point_card(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        index: int,
        text: str,
    ) -> None:
        left, top, right, bottom = box
        draw.rounded_rectangle(box, radius=22, fill=self.card, outline=self.line, width=2)
        draw.ellipse((left + 18, top + 18, left + 62, top + 62), fill=self.accent)
        marker = str(index)
        marker_w = text_width(draw, marker, self.font_small_bold)
        draw.text(
            (left + 40 - marker_w // 2, top + 27),
            marker,
            font=self.font_small_bold,
            fill=self.card,
        )
        lines = wrap_text(draw, text, self.font_body, right - left - 106, 3)
        draw_lines(draw, lines, (left + 80, top + 20), self.font_body, self.ink, 4)

    def _footer(self, draw: ImageDraw.ImageDraw) -> None:
        margin = self.brand.canvas.safe_margin
        y = self.height - self.brand.layout.footer_height
        draw.line((margin, y, self.width - margin, y), fill=self.line, width=2)
        draw.text(
            (margin, y + 12),
            self.brand.copywriting.footer_left,
            font=self.font_small,
            fill=self.muted,
        )
        right = self.brand.copywriting.footer_right
        draw.text(
            (self.width - margin - text_width(draw, right, self.font_small), y + 12),
            right,
            font=self.font_small,
            fill=self.muted,
        )


def render_brand_preview(brand: BrandSpec, output_path: Path) -> None:
    renderer = Renderer(brand)
    slide = SlidePlan.model_validate(
        {
            "index": 1,
            "kind": "cover",
            "headline": "品牌校准页｜固定骨架与受控变化",
            "subheadline": brand.copywriting.tagline,
            "body_points": ["固定色彩", "固定排版", "固定签名"],
            "visual": {
                "primary_subject": "品牌视觉样张",
                "exact_count": 3,
                "must_show": ["色彩", "留白", "构图"],
                "must_not_show": ["文字"],
            },
        }
    )
    renderer.render_slide(slide=slide, output_path=output_path, total_slides=1, raw_image_path=None)

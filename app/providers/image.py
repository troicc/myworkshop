from __future__ import annotations

import base64
import hashlib
import math
import random
from pathlib import Path
from typing import Protocol

import httpx
from PIL import Image, ImageDraw, ImageFilter

from app.brand import BrandSpec
from app.config import Settings
from app.models import VisualBrief
from app.providers.text import ProviderError, _endpoint


class ImageProvider(Protocol):
    name: str

    def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        visual: VisualBrief,
        brand: BrandSpec,
        reference_paths: list[Path],
    ) -> None: ...


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _parse_size(size: str) -> tuple[int, int]:
    try:
        width, height = size.lower().split("x", 1)
        return int(width), int(height)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"invalid image size: {size}") from exc


class MockImageProvider:
    """Deterministic, text-free visual placeholders for local end-to-end tests."""

    name = "mock"

    def __init__(self, size: str = "1024x1536") -> None:
        self.size = _parse_size(size)

    def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        visual: VisualBrief,
        brand: BrandSpec,
        reference_paths: list[Path],
    ) -> None:
        seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        width, height = self.size
        paper = _hex(brand.palette.paper)
        primary = _hex(brand.palette.primary)
        accent = _hex(brand.palette.accent)
        card = _hex(brand.palette.card)
        muted = _hex(brand.palette.muted)

        image = Image.new("RGB", (width, height), paper)
        draw = ImageDraw.Draw(image, "RGBA")

        # Soft editorial field.
        for _ in range(24):
            radius = rng.randint(width // 10, width // 3)
            x = rng.randint(-radius, width)
            y = rng.randint(-radius, height)
            color = rng.choice([primary, accent, card, muted])
            draw.ellipse((x, y, x + radius, y + radius), fill=(*color, rng.randint(8, 26)))
        image = image.filter(ImageFilter.GaussianBlur(radius=max(4, width // 150)))
        draw = ImageDraw.Draw(image, "RGBA")

        # Table plane and one hero vessel.
        horizon = int(height * 0.58)
        draw.polygon(
            [(0, horizon), (width, int(height * 0.52)), (width, height), (0, height)],
            fill=(*_hex("#DDC9A8"), 210),
        )
        cx = int(width * (0.48 if visual.text_safe_area != "left" else 0.68))
        cy = int(height * 0.70)
        vessel_w = int(width * 0.60)
        vessel_h = int(height * 0.23)
        draw.ellipse(
            (cx - vessel_w // 2 + 18, cy - vessel_h // 2 + 22, cx + vessel_w // 2 + 18, cy + vessel_h // 2 + 22),
            fill=(61, 43, 28, 45),
        )
        draw.ellipse(
            (cx - vessel_w // 2, cy - vessel_h // 2, cx + vessel_w // 2, cy + vessel_h // 2),
            fill=(*card, 255),
            outline=(*primary, 120),
            width=max(2, width // 300),
        )
        inner = int(vessel_w * 0.82)
        draw.ellipse(
            (cx - inner // 2, cy - int(vessel_h * 0.32), cx + inner // 2, cy + int(vessel_h * 0.32)),
            fill=(*_hex("#E9D79F"), 255),
        )

        count = visual.exact_count or min(max(len(visual.must_show), 5), 10)
        count = max(3, min(count, 14))
        food_colors = [accent, primary, _hex("#D99A43"), _hex("#F2CC5C"), _hex("#765238")]
        for index in range(count):
            angle = (2 * math.pi * index / count) + rng.uniform(-0.25, 0.25)
            radius = rng.uniform(inner * 0.08, inner * 0.34)
            px = cx + int(math.cos(angle) * radius)
            py = cy + int(math.sin(angle) * radius * 0.45)
            size = rng.randint(width // 34, width // 20)
            color = rng.choice(food_colors)
            draw.ellipse((px - size, py - size, px + size, py + size), fill=(*color, 245))

        # Consistent botanical signature, intentionally text-free.
        stem_x = int(width * 0.12)
        draw.arc(
            (stem_x - width // 9, int(height * 0.18), stem_x + width // 3, int(height * 0.75)),
            260,
            85,
            fill=(*primary, 190),
            width=max(5, width // 120),
        )
        for offset in (0.29, 0.35, 0.41):
            y = int(height * offset)
            draw.ellipse(
                (stem_x, y, stem_x + width // 10, y + height // 18),
                fill=(*primary, 110),
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)


class ManualImageProvider(MockImageProvider):
    """Creates a neutral placeholder while preserving the production prompt."""

    name = "manual"


class OpenAIImageProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.image_api_key:
            raise ValueError("Image API key is empty")
        self.base_url = settings.image_base_url
        self.api_key = settings.image_api_key
        self.model = settings.image_model
        self.size = settings.image_size
        self.quality = settings.image_quality
        self.output_format = settings.image_output_format
        self.timeout = settings.request_timeout
        self.use_reference_edit = settings.image_use_reference_edit

    def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        visual: VisualBrief,
        brand: BrandSpec,
        reference_paths: list[Path],
    ) -> None:
        if self.use_reference_edit and reference_paths:
            try:
                content = self._edit(prompt, reference_paths[:4])
            except ProviderError:
                content = self._generate(prompt)
        else:
            content = self._generate(prompt)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)

    def _generate(self, prompt: str) -> bytes:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "quality": self.quality,
            "output_format": self.output_format,
            "n": 1,
        }
        response = self._post_json("images/generations", payload)
        return self._extract_image(response)

    def _edit(self, prompt: str, references: list[Path]) -> bytes:
        url = _endpoint(self.base_url, "images/edits")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "quality": self.quality,
            "output_format": self.output_format,
        }
        opened = []
        files = []
        try:
            for path in references:
                handle = path.open("rb")
                opened.append(handle)
                files.append(("image[]", (path.name, handle, "image/png")))
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, data=data, files=files)
        except httpx.HTTPError as exc:
            raise ProviderError(f"image edit request failed: {exc}") from exc
        finally:
            for handle in opened:
                handle.close()
        if response.status_code >= 400:
            raise ProviderError(f"image edit HTTP {response.status_code}: {response.text[:1000]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("image edit returned non-JSON response") from exc
        return self._extract_image(payload)

    def _post_json(self, path: str, payload: dict) -> dict:
        url = _endpoint(self.base_url, path)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"image request failed: {exc}") from exc
        if response.status_code >= 400:
            # Some compatible endpoints reject output_format/n. Retry a minimal payload.
            minimal = {key: payload[key] for key in ("model", "prompt", "size") if key in payload}
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=headers, json=minimal)
            except httpx.HTTPError as exc:
                raise ProviderError(f"image request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(f"image HTTP {response.status_code}: {response.text[:1000]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("image endpoint returned non-JSON response") from exc
        if not isinstance(data, dict):
            raise ProviderError("image response root must be an object")
        return data

    def _extract_image(self, payload: dict) -> bytes:
        try:
            item = payload["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"unexpected image response: {payload!r}") from exc
        encoded = item.get("b64_json") if isinstance(item, dict) else None
        if encoded:
            try:
                return base64.b64decode(encoded)
            except ValueError as exc:
                raise ProviderError("invalid base64 image payload") from exc
        url = item.get("url") if isinstance(item, dict) else None
        if url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.content
            except httpx.HTTPError as exc:
                raise ProviderError(f"failed to download generated image: {exc}") from exc
        raise ProviderError("image response contains neither b64_json nor url")


def build_image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider == "mock":
        return MockImageProvider(settings.image_size)
    if settings.image_provider == "manual":
        return ManualImageProvider(settings.image_size)
    return OpenAIImageProvider(settings)

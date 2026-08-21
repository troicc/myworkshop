from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageStat

from app.brand import BrandSpec
from app.config import Settings
from app.models import CriticReport, VisualBrief
from app.providers.text import ProviderError, _endpoint, extract_json


class ImageCritic:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def review(
        self,
        *,
        image_path: Path,
        visual: VisualBrief,
        brand: BrandSpec,
        reference_paths: list[Path],
    ) -> CriticReport:
        local = self._local_review(image_path, reference_paths)
        if not local.passed or self.settings.vision_provider == "off":
            return local
        try:
            remote = self._remote_review(image_path, visual, brand)
        except Exception as exc:  # critic failure must not discard a valid asset
            local.observations.append(f"远程视觉审查不可用：{exc}")
            return local
        combined_score = min(local.score, remote.score)
        issues = [*local.issues, *remote.issues]
        observations = [*local.observations, *remote.observations]
        return CriticReport(
            passed=local.passed and remote.passed,
            score=combined_score,
            issues=issues,
            observations=observations,
            retry_instruction=remote.retry_instruction or local.retry_instruction,
        )

    def _local_review(self, image_path: Path, reference_paths: list[Path]) -> CriticReport:
        issues: list[str] = []
        observations: list[str] = []
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                width, height = image.size
                if min(width, height) < 512:
                    issues.append(f"分辨率过低：{width}×{height}")
                ratio = width / height
                if not 0.58 <= ratio <= 0.82:
                    issues.append(f"画幅比例异常：{ratio:.3f}，建议使用竖版素材")
                stat = ImageStat.Stat(image.resize((128, 128)))
                variance = sum(stat.var) / 3
                if variance < 20:
                    issues.append("图片信息量过低，可能是空白图或纯色图")
                observations.append(f"素材尺寸 {width}×{height}，像素方差 {variance:.1f}")
                if reference_paths:
                    distance = self._reference_distance(image, reference_paths)
                    observations.append(f"与批准参考图的平均色彩距离 {distance:.1f}")
        except Exception as exc:
            return CriticReport(
                passed=False,
                score=0,
                issues=[f"无法读取图片：{exc}"],
                retry_instruction="重新生成一个有效 PNG/JPEG 竖版图片。",
            )
        passed = not issues
        score = max(0, 100 - 25 * len(issues))
        retry = "；".join(issues)
        if retry:
            retry = f"修正上一版素材：{retry}。保持其他已满足要求不变。"
        return CriticReport(
            passed=passed,
            score=score,
            issues=issues,
            observations=observations,
            retry_instruction=retry,
        )

    @staticmethod
    def _reference_distance(image: Image.Image, reference_paths: list[Path]) -> float:
        target = ImageStat.Stat(image.resize((64, 64))).mean
        distances: list[float] = []
        for path in reference_paths[:12]:
            try:
                with Image.open(path) as ref:
                    mean = ImageStat.Stat(ref.convert("RGB").resize((64, 64))).mean
            except Exception:
                continue
            distances.append(sum(abs(a - b) for a, b in zip(target, mean, strict=True)) / 3)
        return sum(distances) / len(distances) if distances else 0.0

    def _remote_review(
        self, image_path: Path, visual: VisualBrief, brand: BrandSpec
    ) -> CriticReport:
        if not self.settings.vision_api_key:
            raise ProviderError("VISION API key is empty")
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        data_url = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"
        expected = visual.model_dump(mode="json")
        prompt = (
            "你是严格的视觉质检员。根据视觉合同检查图片，不评价文案。"
            "重点检查主体、数量、状态、必须出现、禁止出现、构图留白和品牌风格。"
            "只返回 JSON：passed(boolean), score(0-100), issues(string[]), "
            "observations(string[]), retry_instruction(string)。\n"
            f"视觉合同：{json.dumps(expected, ensure_ascii=False)}\n"
            f"品牌锚点：{brand.prompt_anchor()}"
        )
        payload: dict[str, Any] = {
            "model": self.settings.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        url = _endpoint(self.settings.vision_base_url, "chat/completions")
        headers = {
            "Authorization": f"Bearer {self.settings.vision_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.settings.request_timeout) as client:
            response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            payload.pop("response_format", None)
            with httpx.Client(timeout=self.settings.request_timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise ProviderError(f"vision HTTP {response.status_code}: {response.text[:800]}")
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = extract_json(content)
        return CriticReport.model_validate(parsed)

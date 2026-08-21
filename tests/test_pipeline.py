from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.config import Settings
from app.models import ProjectStatus, StoryBrief
from app.pipeline import ContentPipeline


def test_mock_pipeline_end_to_end(tmp_path: Path) -> None:
    settings = Settings(
        workspace_root=tmp_path / "workspace",
        brand_file=Path("brand/default/brand.yaml"),
        llm_provider="mock",
        image_provider="mock",
        image_size="512x768",
        vision_provider="off",
        max_image_retries=0,
    )
    manifest = ContentPipeline(settings).generate(
        StoryBrief(
            title="早八来不及做饭｜8套10分钟早餐",
            audience="上班族",
            scenario="工作日早晨",
            objective="给出可执行轮换方案",
            slide_count=4,
        )
    )
    assert manifest.status == ProjectStatus.completed, manifest.error
    project_dir = settings.workspace_root / "projects" / manifest.project_id
    assert (project_dir / "plan.json").exists()
    assert (project_dir / "export.zip").exists()
    assert len(manifest.output_files) == 4
    for relative in manifest.output_files:
        with Image.open(project_dir / relative) as image:
            assert image.size == (1080, 1440)
    plan = json.loads((project_dir / "plan.json").read_text(encoding="utf-8"))
    assert len(plan["slides"]) == 4
    assert plan["style_version"].startswith("下班好好吃@1.0.0+")
    history = (settings.workspace_root / "history.jsonl").read_text(encoding="utf-8")
    assert manifest.project_id in history

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.brand import BrandSpec, load_brand
from app.compliance import scan_content
from app.config import Settings
from app.models import ContentPlan, ProjectManifest, ProjectStatus, StoryBrief
from app.planner import ContentPlanner
from app.prompt_compiler import PromptCompiler
from app.providers.image import ImageProvider, build_image_provider
from app.providers.vision import ImageCritic
from app.render import Renderer
from app.store import ProjectStore


class ContentPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_directories()
        self.store = ProjectStore(settings.workspace_root)
        self.brand: BrandSpec = load_brand(settings.brand_file)
        self.planner = ContentPlanner(settings)
        self.compiler = PromptCompiler()
        self.image_provider: ImageProvider = build_image_provider(settings)
        self.critic = ImageCritic(settings)
        self.renderer = Renderer(self.brand)

    def generate(self, brief: StoryBrief) -> ProjectManifest:
        project_dir, manifest = self.store.create_project(brief.title)
        manifest.brand_name = self.brand.name
        manifest.brand_version = self.brand.version
        manifest.brand_fingerprint = self.brand.fingerprint
        manifest.llm_provider = self.settings.llm_provider
        manifest.image_provider = self.settings.image_provider
        manifest.slide_count = brief.slide_count
        self.store.save_manifest(manifest)
        self.store.write_json(project_dir / "brief.json", brief.model_dump(mode="json"))

        try:
            self.store.update_status(manifest.project_id, ProjectStatus.planning)
            history = self.store.recent_history(limit=12)
            plan = self.planner.plan(brief=brief, brand=self.brand, history=history)
            self.store.write_json(project_dir / "plan.json", plan.model_dump(mode="json"))

            compliance = scan_content(brief, plan)
            self.store.write_json(
                project_dir / "compliance.json", compliance.model_dump(mode="json")
            )

            self.store.update_status(manifest.project_id, ProjectStatus.generating)
            references = self.store.list_references()
            for slide in plan.slides:
                if slide.visual is None:
                    continue
                raw_path = project_dir / "raw" / f"{slide.index:02d}.png"
                compiled = self.compiler.compile(
                    plan=plan,
                    slide=slide,
                    brand=self.brand,
                    history=history,
                )
                self.store.write_text(
                    project_dir / "prompts" / f"{slide.index:02d}.txt", compiled.text + "\n"
                )
                self.store.write_json(
                    project_dir / "prompts" / f"{slide.index:02d}.json",
                    {
                        "slide": slide.index,
                        "sha256": compiled.sha256,
                        "brand_style_id": self.brand.style_id,
                        "visual_contract": slide.visual.model_dump(mode="json"),
                    },
                )
                self.image_provider.generate(
                    prompt=compiled.text,
                    output_path=raw_path,
                    visual=slide.visual,
                    brand=self.brand,
                    reference_paths=references,
                )

                self.store.update_status(manifest.project_id, ProjectStatus.reviewing)
                review = self.critic.review(
                    image_path=raw_path,
                    visual=slide.visual,
                    brand=self.brand,
                    reference_paths=references,
                )
                attempts = 0
                while not review.passed and attempts < self.settings.max_image_retries:
                    attempts += 1
                    corrected = self.compiler.compile(
                        plan=plan,
                        slide=slide,
                        brand=self.brand,
                        history=history,
                        retry_instruction=review.retry_instruction,
                    )
                    self.store.write_text(
                        project_dir / "prompts" / f"{slide.index:02d}-retry-{attempts}.txt",
                        corrected.text + "\n",
                    )
                    self.image_provider.generate(
                        prompt=corrected.text,
                        output_path=raw_path,
                        visual=slide.visual,
                        brand=self.brand,
                        reference_paths=references,
                    )
                    review = self.critic.review(
                        image_path=raw_path,
                        visual=slide.visual,
                        brand=self.brand,
                        reference_paths=references,
                    )
                self.store.write_json(
                    project_dir / "reviews" / f"{slide.index:02d}.json",
                    {**review.model_dump(mode="json"), "attempts": attempts},
                )

            self.store.update_status(manifest.project_id, ProjectStatus.rendering)
            outputs = self._render(project_dir, plan)
            self._write_caption(project_dir, plan, compliance.model_dump(mode="json"))

            manifest = self.store.load_manifest(manifest.project_id)
            manifest.output_files = [path.relative_to(project_dir).as_posix() for path in outputs]
            manifest.slide_count = len(plan.slides)
            manifest.touch(ProjectStatus.completed)
            self.store.save_manifest(manifest)
            self.store.build_export(manifest.project_id)
            self._append_history(manifest, plan)
            return manifest
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            self.store.write_text(
                project_dir / "error.txt",
                error_text + "\n\n" + traceback.format_exc(limit=12),
            )
            return self.store.update_status(
                manifest.project_id, ProjectStatus.failed, error=error_text
            )

    def rerender(self, project_id: str) -> ProjectManifest:
        project_dir = self.store.project_dir(project_id)
        plan = ContentPlan.model_validate(self.store.read_json(project_dir / "plan.json"))
        self.store.update_status(project_id, ProjectStatus.rendering)
        try:
            outputs = self._render(project_dir, plan)
            manifest = self.store.load_manifest(project_id)
            manifest.output_files = [path.relative_to(project_dir).as_posix() for path in outputs]
            manifest.touch(ProjectStatus.completed)
            manifest.error = ""
            self.store.save_manifest(manifest)
            self.store.build_export(project_id)
            return manifest
        except Exception as exc:
            return self.store.update_status(
                project_id,
                ProjectStatus.failed,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _render(self, project_dir: Path, plan: ContentPlan) -> list[Path]:
        outputs: list[Path] = []
        total = len(plan.slides)
        for slide in plan.slides:
            raw = project_dir / "raw" / f"{slide.index:02d}.png"
            output = project_dir / "output" / f"{slide.index:02d}-{slide.kind}.png"
            self.renderer.render_slide(
                slide=slide,
                output_path=output,
                total_slides=total,
                raw_image_path=raw if raw.exists() else None,
            )
            outputs.append(output)
        return outputs

    def _write_caption(
        self, project_dir: Path, plan: ContentPlan, compliance: dict[str, Any]
    ) -> None:
        tags = " ".join(f"#{tag.lstrip('#')}" for tag in plan.tags)
        warnings = [
            f"- [{flag['severity']}] {flag['message']} 建议：{flag['suggestion']}"
            for flag in compliance.get("flags", [])
        ]
        warning_block = "\n".join(warnings) or "- 未命中内置高风险关键词；仍需人工核验事实。"
        caption = (
            f"{plan.caption.strip()}\n\n{tags}\n\n"
            "---\n"
            "发布前检查（不建议直接复制到正文）：\n"
            f"{warning_block}\n"
        )
        self.store.write_text(project_dir / "caption.md", caption)

    def _append_history(self, manifest: ProjectManifest, plan: ContentPlan) -> None:
        visual_subjects = [
            slide.visual.primary_subject for slide in plan.slides if slide.visual is not None
        ]
        self.store.append_history(
            {
                "project_id": manifest.project_id,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "title": plan.project_title,
                "core_promise": plan.core_promise,
                "visual_subjects": visual_subjects,
                "slide_kinds": [slide.kind for slide in plan.slides],
                "brand_style_id": self.brand.style_id,
            }
        )

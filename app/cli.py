from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import uvicorn
from PIL import features

from app.brand import load_brand
from app.config import Settings, get_settings
from app.models import ProjectStatus, StoryBrief
from app.pipeline import ContentPipeline
from app.render import render_brand_preview, resolve_font


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="myworkshop", description="AI内容工作站")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="启动网页工作台")
    run.add_argument("--host", default=None)
    run.add_argument("--port", type=int, default=None)
    run.add_argument("--reload", action="store_true")

    subparsers.add_parser("demo", help="使用零成本 Mock Provider 跑完整流程")

    generate = subparsers.add_parser("generate", help="按当前 .env 生成项目")
    generate.add_argument("--title", required=True)
    generate.add_argument("--audience", default="忙碌的普通用户")
    generate.add_argument("--scenario", default="日常可执行的生活场景")
    generate.add_argument("--objective", default="提供清晰、可收藏、可执行的解决方案")
    generate.add_argument("--slides", type=int, default=5)
    generate.add_argument("--source", action="append", default=[])

    rerender = subparsers.add_parser("rerender", help="使用 raw/ 中的素材重新排版")
    rerender.add_argument("project_id")

    preview = subparsers.add_parser("brand-preview", help="生成品牌骨架预览")
    preview.add_argument("--output", default="workspace/brand-preview.png")

    subparsers.add_parser("doctor", help="检查配置、字体与图片能力")
    return parser


def _print_manifest(manifest) -> int:
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if manifest.status == ProjectStatus.failed:
        return 1
    return 0


def run_demo() -> int:
    base = get_settings()
    settings = base.model_copy(
        update={
            "llm_provider": "mock",
            "image_provider": "mock",
            "vision_provider": "off",
        }
    )
    pipeline = ContentPipeline(settings)
    manifest = pipeline.generate(
        StoryBrief(
            title="早八来不及做饭｜8套10分钟早餐",
            audience="需要准时出门的上班族",
            scenario="工作日早晨可用时间不超过10分钟",
            objective="给出可以轮换、容易准备的早餐组合",
            slide_count=5,
        )
    )
    return _print_manifest(manifest)


def doctor(settings: Settings) -> int:
    try:
        brand = load_brand(settings.brand_file)
        font = resolve_font(32, bold=False, extra_candidates=brand.typography.sans_candidates)
        font_path = getattr(font, "path", "built-in")
        report = {
            "workspace": str(settings.workspace_root.resolve()),
            "brand_file": str(settings.brand_file.resolve()),
            "brand_style_id": brand.style_id,
            "llm_provider": settings.llm_provider,
            "image_provider": settings.image_provider,
            "vision_provider": settings.vision_provider,
            "font": str(font_path),
            "pillow_webp": features.check("webp"),
            "ready": True,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.command == "run":
        uvicorn.run(
            "app.web:app",
            host=args.host or settings.host,
            port=args.port or settings.port,
            reload=args.reload,
        )
        return
    if args.command == "demo":
        raise SystemExit(run_demo())
    if args.command == "doctor":
        raise SystemExit(doctor(settings))
    if args.command == "brand-preview":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        render_brand_preview(load_brand(settings.brand_file), output)
        print(output.resolve())
        return

    pipeline = ContentPipeline(settings)
    if args.command == "generate":
        brief = StoryBrief(
            title=args.title,
            audience=args.audience,
            scenario=args.scenario,
            objective=args.objective,
            slide_count=args.slides,
            source_notes=args.source,
        )
        raise SystemExit(_print_manifest(pipeline.generate(brief)))
    if args.command == "rerender":
        raise SystemExit(_print_manifest(pipeline.rerender(args.project_id)))
    print("unknown command", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()

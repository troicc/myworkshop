from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.brand import load_brand
from app.config import get_settings
from app.models import GenerateRequest, ProjectStatus
from app.pipeline import ContentPipeline
from app.store import ProjectStore

PACKAGE_ROOT = Path(__file__).resolve().parent
settings = get_settings()
store = ProjectStore(settings.workspace_root)
brand = load_brand(settings.brand_file)

app = FastAPI(title="MyWorkshop", version="0.1.0")
app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")


def new_pipeline() -> ContentPipeline:
    return ContentPipeline(settings)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "brand": brand,
            "providers": {
                "llm": settings.llm_provider,
                "image": settings.image_provider,
                "vision": settings.vision_provider,
            },
        },
    )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "brand_style_id": brand.style_id,
        "llm_provider": settings.llm_provider,
        "image_provider": settings.image_provider,
    }


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return [item.model_dump(mode="json") for item in store.list_projects(limit=50)]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        manifest = store.load_manifest(project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found") from None
    return manifest.model_dump(mode="json")


@app.post("/api/generate")
async def generate(request: GenerateRequest) -> JSONResponse:
    pipeline = new_pipeline()
    manifest = await asyncio.to_thread(pipeline.generate, request)
    code = 200 if manifest.status == ProjectStatus.completed else 500
    return JSONResponse(manifest.model_dump(mode="json"), status_code=code)


@app.post("/api/projects/{project_id}/rerender")
async def rerender(project_id: str) -> JSONResponse:
    try:
        pipeline = new_pipeline()
        manifest = await asyncio.to_thread(pipeline.rerender, project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found") from None
    code = 200 if manifest.status == ProjectStatus.completed else 500
    return JSONResponse(manifest.model_dump(mode="json"), status_code=code)


@app.post("/api/references")
async def upload_reference(file: Annotated[UploadFile, File()]) -> dict:
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="reference image exceeds 20 MB")
    try:
        target = store.save_reference(file.filename or "reference.png", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"saved": target.name}


@app.post("/api/projects/{project_id}/raw/{slide_index}")
async def upload_raw(project_id: str, slide_index: int, file: Annotated[UploadFile, File()]) -> dict:
    if not 1 <= slide_index <= 20:
        raise HTTPException(status_code=400, detail="invalid slide index")
    suffix = Path(file.filename or "image.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="image must be png, jpg, jpeg, or webp")
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image exceeds 30 MB")
    try:
        project_dir = store.project_dir(project_id)
        if not project_dir.exists():
            raise FileNotFoundError
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found") from None
    temp = project_dir / "raw" / f".{slide_index:02d}-upload{suffix}"
    temp.write_bytes(content)
    try:
        from PIL import Image

        with Image.open(temp) as source:
            source.convert("RGB").save(project_dir / "raw" / f"{slide_index:02d}.png", "PNG")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid image: {exc}") from exc
    finally:
        temp.unlink(missing_ok=True)
    return {"saved": f"raw/{slide_index:02d}.png"}


@app.get("/files/{project_id}/{relative_path:path}")
def project_file(project_id: str, relative_path: str):
    try:
        root = store.project_dir(project_id).resolve()
    except ValueError:
        raise HTTPException(status_code=404, detail="project not found") from None
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)

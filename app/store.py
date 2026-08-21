from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import ProjectManifest, ProjectStatus, ProjectSummary


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.projects_root = root / "projects"
        self.references_root = root / "references"
        self.history_file = root / "history.jsonl"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.references_root.mkdir(parents=True, exist_ok=True)

    def new_project_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{secrets.token_hex(3)}"

    def project_dir(self, project_id: str) -> Path:
        self._validate_id(project_id)
        return self.projects_root / project_id

    def create_project(self, title: str) -> tuple[Path, ProjectManifest]:
        project_id = self.new_project_id()
        project_dir = self.project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=False)
        for name in ("prompts", "raw", "reviews", "output"):
            (project_dir / name).mkdir()
        manifest = ProjectManifest(project_id=project_id, title=title)
        self.save_manifest(manifest)
        return project_dir, manifest

    def save_manifest(self, manifest: ProjectManifest) -> None:
        self.write_json(
            self.project_dir(manifest.project_id) / "manifest.json",
            manifest.model_dump(mode="json"),
        )

    def load_manifest(self, project_id: str) -> ProjectManifest:
        return ProjectManifest.model_validate(
            self.read_json(self.project_dir(project_id) / "manifest.json")
        )

    def update_status(
        self, project_id: str, status: ProjectStatus, *, error: str = ""
    ) -> ProjectManifest:
        manifest = self.load_manifest(project_id)
        manifest.touch(status)
        manifest.error = error
        self.save_manifest(manifest)
        return manifest

    def write_json(self, path: Path, data: Any) -> None:
        self._atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, path: Path, text: str) -> None:
        self._atomic_write(path, text)

    def _atomic_write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temp_name, path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def list_projects(self, limit: int = 30) -> list[ProjectSummary]:
        manifests: list[ProjectSummary] = []
        for path in self.projects_root.glob("*/manifest.json"):
            try:
                manifest = ProjectManifest.model_validate(self.read_json(path))
            except Exception:
                continue
            manifests.append(
                ProjectSummary(
                    project_id=manifest.project_id,
                    title=manifest.title,
                    status=manifest.status,
                    created_at=manifest.created_at,
                    output_files=manifest.output_files,
                )
            )
        manifests.sort(key=lambda item: item.created_at, reverse=True)
        return manifests[:limit]

    def append_history(self, entry: dict[str, Any]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        # O_APPEND keeps each short JSONL write atomic on local filesystems.
        fd = os.open(self.history_file, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)

    def recent_history(self, limit: int = 12) -> list[dict[str, Any]]:
        if not self.history_file.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.history_file.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-limit:]

    def list_references(self) -> list[Path]:
        suffixes = {".png", ".jpg", ".jpeg", ".webp"}
        return sorted(
            path for path in self.references_root.iterdir() if path.suffix.lower() in suffixes
        )

    def save_reference(self, filename: str, content: bytes) -> Path:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("reference image must be png, jpg, jpeg, or webp")
        target = self.references_root / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe_name}"
        target.write_bytes(content)
        return target

    def build_export(self, project_id: str) -> Path:
        project_dir = self.project_dir(project_id)
        target = project_dir / "export.zip"
        include_names = {
            "brief.json",
            "plan.json",
            "manifest.json",
            "compliance.json",
            "caption.md",
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in project_dir.rglob("*"):
                if not path.is_file() or path == target:
                    continue
                relative = path.relative_to(project_dir)
                if relative.name in include_names or relative.parts[0] in {
                    "prompts",
                    "raw",
                    "reviews",
                    "output",
                }:
                    archive.write(path, relative.as_posix())
        return target

    def replace_raw_image(self, project_id: str, slide_index: int, source: Path) -> Path:
        project_dir = self.project_dir(project_id)
        target = project_dir / "raw" / f"{slide_index:02d}.png"
        with source.open("rb") as reader, target.open("wb") as writer:
            shutil.copyfileobj(reader, writer)
        return target

    @staticmethod
    def _validate_id(project_id: str) -> None:
        if not project_id or any(char not in "0123456789abcdef-" for char in project_id.lower()):
            raise ValueError("invalid project id")


def relative_strings(paths: Iterable[Path], base: Path) -> list[str]:
    return [path.relative_to(base).as_posix() for path in paths]

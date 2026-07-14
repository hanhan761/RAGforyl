from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ragforyl import __version__
from ragforyl.answering import AnswerService
from ragforyl.config import SUPPORTED_EXTENSIONS, Settings
from ragforyl.io import read_json, safe_filename
from ragforyl.pipeline import BuildPipeline
from ragforyl.retrieval import KnowledgeBase


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)
    generate_answer: bool = True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    build_lock = threading.Lock()
    web_dir = Path(__file__).resolve().parent / "web"
    app = FastAPI(title="RAGforyl", version=__version__)
    app.mount("/assets", StaticFiles(directory=web_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def homepage() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/status")
    def status() -> dict[str, object]:
        manifest_path = settings.index_dir / "manifest.json"
        manifest = read_json(manifest_path) if manifest_path.exists() else None
        return {
            "version": __version__,
            "index_ready": manifest is not None,
            "manifest": manifest,
            "settings": settings.public_summary(),
            "sources": _source_listing(settings.source_dir),
        }

    @app.post("/api/sources")
    async def upload_sources(
        files: Annotated[list[UploadFile], File()],
    ) -> dict[str, object]:
        if not files:
            raise HTTPException(status_code=400, detail="请选择至少一个文件")
        saved = []
        for upload in files:
            filename = safe_filename(upload.filename or "document.txt")
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                raise HTTPException(
                    status_code=415, detail=f"不支持的文件类型：{suffix or 'unknown'}"
                )
            target = _available_target(settings.source_dir, filename)
            size = 0
            try:
                with target.open("wb") as handle:
                    while data := await upload.read(1024 * 1024):
                        size += len(data)
                        if size > settings.max_upload_mb * 1024 * 1024:
                            raise HTTPException(
                                status_code=413,
                                detail=f"单文件不能超过 {settings.max_upload_mb} MB",
                            )
                        handle.write(data)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            finally:
                await upload.close()
            saved.append({"name": target.name, "size_bytes": size})
        return {"saved": saved, "sources": _source_listing(settings.source_dir)}

    @app.delete("/api/sources/{filename}")
    def delete_source(filename: str) -> dict[str, object]:
        safe = safe_filename(filename)
        target = (settings.source_dir / safe).resolve()
        if target.parent != settings.source_dir.resolve() or not target.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        target.unlink()
        return {"deleted": safe, "sources": _source_listing(settings.source_dir)}

    @app.post("/api/build")
    async def build() -> dict[str, object]:
        if not build_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="知识图谱正在构建，请稍候")
        try:
            result = await asyncio.to_thread(BuildPipeline(settings).build)
            return {"manifest": result.manifest, "quality": result.quality}
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            build_lock.release()

    @app.post("/api/query")
    async def query_knowledge(request: QueryRequest) -> dict[str, object]:
        try:
            knowledge_base = KnowledgeBase(settings.index_dir)
            if request.generate_answer:
                return await asyncio.to_thread(
                    AnswerService(settings, knowledge_base).answer,
                    request.question,
                    top_k=request.top_k,
                )
            retrieval = await asyncio.to_thread(
                knowledge_base.search,
                request.question,
                top_k=request.top_k,
            )
            return {"answer": "", "answer_mode": "retrieval_only", "retrieval": retrieval}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail="请先构建知识图谱") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/graph")
    def graph(limit: int = Query(default=120, ge=1, le=500)) -> dict[str, object]:
        graph_path = settings.index_dir / "graph.json"
        if not graph_path.exists():
            raise HTTPException(status_code=409, detail="请先构建知识图谱")
        payload = read_json(graph_path)
        nodes = payload["nodes"][:limit]
        node_ids = {node["id"] for node in nodes}
        edges = [
            edge
            for edge in payload["edges"]
            if edge["source"] in node_ids and edge["target"] in node_ids
        ][: limit * 3]
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(payload["nodes"]),
            "total_edges": len(payload["edges"]),
        }

    @app.delete("/api/index")
    def delete_index() -> dict[str, bool]:
        if settings.index_dir.exists():
            shutil.rmtree(settings.index_dir)
        settings.index_dir.mkdir(parents=True, exist_ok=True)
        return {"deleted": True}

    return app


def _source_listing(source_dir: Path) -> list[dict[str, object]]:
    return [
        {"name": path.name, "size_bytes": path.stat().st_size}
        for path in sorted(source_dir.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def _available_target(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


app = create_app()

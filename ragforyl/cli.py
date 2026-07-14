from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from ragforyl import __version__
from ragforyl.answering import AnswerService
from ragforyl.config import SUPPORTED_EXTENSIONS, Settings
from ragforyl.exporter import export_graph
from ragforyl.pipeline import BuildPipeline
from ragforyl.retrieval import KnowledgeBase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ragforyl",
        description="从文档构建可追溯的知识图谱，并进行 Graph RAG 检索。",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="读取文档并构建知识图谱索引")
    _add_paths(build)

    query = subparsers.add_parser("query", help="只执行知识图谱检索")
    query.add_argument("question")
    query.add_argument("--top-k", type=int, default=6)
    query.add_argument("--index", type=Path)
    query.add_argument("--json", action="store_true", dest="as_json")

    ask = subparsers.add_parser("ask", help="检索并生成带来源回答")
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int, default=6)
    ask.add_argument("--index", type=Path)
    ask.add_argument("--json", action="store_true", dest="as_json")

    serve = subparsers.add_parser("serve", help="启动中文网页界面")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--data", type=Path)
    serve.add_argument("--open-browser", action="store_true")

    doctor = subparsers.add_parser("doctor", help="检查环境、数据目录与索引")
    doctor.add_argument("--data", type=Path)

    export = subparsers.add_parser("export", help="导出 CSV 或 GraphML")
    export.add_argument("--index", type=Path)
    export.add_argument("--output", type=Path, default=Path("exports"))
    export.add_argument("--format", choices=("csv", "graphml"), default="graphml")
    return parser


def _add_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--index", type=Path)


def main(argv: list[str] | None = None) -> None:
    _configure_console()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            _command_build(args)
        elif args.command == "query":
            _command_query(args)
        elif args.command == "ask":
            _command_ask(args)
        elif args.command == "serve":
            _command_serve(args)
        elif args.command == "doctor":
            _command_doctor(args)
        elif args.command == "export":
            _command_export(args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.from_env(
        data_dir=getattr(args, "data", None),
        source_dir=getattr(args, "source", None),
        index_dir=getattr(args, "index", None),
    )


def _command_build(args: argparse.Namespace) -> None:
    settings = _settings(args)

    def report(stage: str, current: int, total: int) -> None:
        print(f"[{stage}] {current}/{total}")

    result = BuildPipeline(settings).build(progress=report)
    print(json.dumps(result.manifest, ensure_ascii=False, indent=2))
    print(f"\n索引已发布到：{result.index_dir}")


def _command_query(args: argparse.Namespace) -> None:
    settings = Settings.from_env(index_dir=args.index)
    result = KnowledgeBase(settings.index_dir).search(args.question, top_k=args.top_k)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"置信度：{result['confidence']:.0%}")
    for node in result["nodes"]:
        print(f"- {node['name']} [{node['type']}] score={node['score']:.3f}")
    for source in result["sources"]:
        print(f"[{source['reference']}] {source['source_path']} / {source['section']}")


def _command_ask(args: argparse.Namespace) -> None:
    settings = Settings.from_env(index_dir=args.index)
    result = AnswerService(settings, KnowledgeBase(settings.index_dir)).answer(
        args.question,
        top_k=args.top_k,
    )
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(result["answer"])
    for source in result["retrieval"]["sources"]:
        print(f"[{source['reference']}] {source['source_path']} / {source['section']}")


def _command_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from ragforyl.server import create_app

    settings = Settings.from_env(data_dir=args.data)
    if args.open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")


def _command_doctor(args: argparse.Namespace) -> None:
    settings = Settings.from_env(data_dir=args.data)
    settings.ensure_directories()
    source_files = [
        path
        for path in settings.source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    index_ready = (settings.index_dir / "manifest.json").exists()
    print(f"RAGforyl {__version__}")
    print(f"数据目录：{settings.data_dir}")
    print(f"文档数量：{len(source_files)}")
    print(f"索引状态：{'可用' if index_ready else '尚未构建'}")
    print(f"抽取模式：{settings.effective_extraction_mode}")
    print(f"回答模型：{'已配置' if settings.llm_enabled else '未配置（可进行离线检索）'}")


def _command_export(args: argparse.Namespace) -> None:
    settings = Settings.from_env(index_dir=args.index)
    if not (settings.index_dir / "graph.json").exists():
        raise FileNotFoundError("Please build the graph before exporting")
    paths = export_graph(settings.index_dir, args.output.resolve(), args.format)
    for path in paths:
        print(path)

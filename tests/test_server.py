from fastapi.testclient import TestClient

from ragforyl.server import create_app


def test_web_upload_build_query_flow(settings_factory) -> None:
    settings = settings_factory()
    client = TestClient(create_app(settings))

    upload = client.post(
        "/api/sources",
        files={
            "files": (
                "flight.md",
                "# 升力\n\n升力系数是描述升力能力的指标。攻角影响升力系数。",
                "text/markdown",
            )
        },
    )
    build = client.post("/api/build")
    query = client.post(
        "/api/query",
        json={"question": "攻角影响什么？", "top_k": 5, "generate_answer": True},
    )
    graph = client.get("/api/graph")

    assert upload.status_code == 200
    assert build.status_code == 200
    assert build.json()["quality"]["passed"] is True
    assert query.status_code == 200
    assert query.json()["retrieval"]["nodes"]
    assert graph.status_code == 200
    assert graph.json()["total_nodes"] > 0


def test_web_rejects_unsupported_and_oversized_files(settings_factory) -> None:
    settings = settings_factory()
    client = TestClient(create_app(settings))

    unsupported = client.post(
        "/api/sources",
        files={"files": ("payload.exe", b"hello", "application/octet-stream")},
    )
    oversized = client.post(
        "/api/sources",
        files={"files": ("large.txt", b"x" * (2 * 1024 * 1024 + 1), "text/plain")},
    )

    assert unsupported.status_code == 415
    assert oversized.status_code == 413
    assert not (settings.source_dir / "large.txt").exists()

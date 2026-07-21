"""video_faststart 远程 ComfyUI 节点解析。"""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from services import video_faststart as vfs


@pytest.mark.parametrize(
    "nodes,node_port,expected_base",
    [
        (
            "http://127.0.0.1:8000,https://u1066791-90fc-c93a7df9.westb.seetacloud.com:8443",
            "8443",
            "https://u1066791-90fc-c93a7df9.westb.seetacloud.com:8443",
        ),
        (
            "http://127.0.0.1:8000,https://u1066791-90fc-c93a7df9.westb.seetacloud.com:8443",
            "8000",
            "http://127.0.0.1:8000",
        ),
    ],
)
def test_download_comfy_video_uses_resolve_comfyui_node_url(
    nodes: str, node_port: str, expected_base: str, monkeypatch: pytest.MonkeyPatch
):
    captured: dict[str, str] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @property
        def content(self) -> bytes:
            return b"fake-mp4"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)

    with patch("core.config.settings.comfyui_nodes", nodes):
        path = vfs._download_comfy_video(
            "AIStudio_video_00001_.mp4",
            node_port=node_port,
        )

    assert path is not None
    assert captured["url"].startswith(f"{expected_base}/view?")
    assert "filename=AIStudio_video_00001_.mp4" in captured["url"]


def test_resolve_source_skips_local_when_remote_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """远程 node=8443 时不得命中本地同名旧片。"""
    local_stale = tmp_path / "AIStudio_video_00003.mp4"
    local_stale.write_bytes(b"STALE_LOCAL_3S")
    remote_bytes = b"REMOTE_FULL_10S_CONTENT"
    captured: dict[str, str] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @property
        def content(self) -> bytes:
            return remote_bytes

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(vfs, "_resolve_comfy_output_path", lambda *_a, **_k: local_stale)

    nodes = (
        "http://127.0.0.1:8000,"
        "https://u1066791-a93a-cd311f6b.westc.seetacloud.com:8443"
    )
    with patch("core.config.settings.comfyui_nodes", nodes):
        src, temp_dir = vfs._resolve_source_video_path(
            "/api/view?filename=AIStudio_video_00003.mp4&type=output&node=8443"
        )

    assert src is not None
    assert src.read_bytes() == remote_bytes
    assert src != local_stale
    assert "8443" in captured["url"] or "westc.seetacloud.com" in captured["url"]
    assert temp_dir is not None
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_resolve_source_uses_local_when_local_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_file = tmp_path / "AIStudio_video_00003.mp4"
    local_file.write_bytes(b"LOCAL_OK")
    monkeypatch.setattr(vfs, "_resolve_comfy_output_path", lambda *_a, **_k: local_file)
    monkeypatch.setattr(
        vfs,
        "_download_comfy_video",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not download")),
    )

    nodes = (
        "http://127.0.0.1:8000,"
        "https://u1066791-a93a-cd311f6b.westc.seetacloud.com:8443"
    )
    with patch("core.config.settings.comfyui_nodes", nodes):
        src, temp_dir = vfs._resolve_source_video_path(
            "/api/view?filename=AIStudio_video_00003.mp4&type=output&node=8000"
        )

    assert src == local_file
    assert temp_dir is None

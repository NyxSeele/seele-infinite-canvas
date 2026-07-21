import os

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/network", tags=["network"])

TEST_FILE_SIZE = 100 * 1024 * 1024  # 100 MiB
CHUNK_SIZE = 256 * 1024


def _random_chunk_generator(total_size: int, chunk_size: int):
    remaining = total_size
    while remaining > 0:
        size = min(chunk_size, remaining)
        yield os.urandom(size)
        remaining -= size


@router.get("/test-download")
async def test_download():
    return StreamingResponse(
        _random_chunk_generator(TEST_FILE_SIZE, CHUNK_SIZE),
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(TEST_FILE_SIZE),
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.post("/test-upload")
async def test_upload(request: Request):
    async for _ in request.stream():
        pass
    return {"success": True}

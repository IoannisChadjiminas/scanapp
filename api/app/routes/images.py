from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.recognition.images import ImageError, decode_image, to_jpeg_bytes
from app.recognition.upload import read_upload_limited
from app.schemas import PrepareResponse

router = APIRouter()


def _prepare_jpeg(data: bytes, max_pixels: int) -> PrepareResponse:
    decoded = decode_image(data, max_pixels)
    jpeg = to_jpeg_bytes(decoded.image)
    width, height = decoded.image.size
    return PrepareResponse(
        width=width,
        height=height,
        image_base64=base64.b64encode(jpeg).decode("ascii"),
        converted=decoded.converted or decoded.format_name != "JPEG",
    )


@router.post("/images/prepare", response_model=PrepareResponse)
async def prepare_image(request: Request, image: UploadFile) -> PrepareResponse:
    settings = request.app.state.settings
    data = await read_upload_limited(image, settings.max_upload_bytes)
    try:
        return await request.app.state.loop.run_in_executor(
            request.app.state.image_executor,
            lambda: _prepare_jpeg(data, settings.max_image_pixels),
        )
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

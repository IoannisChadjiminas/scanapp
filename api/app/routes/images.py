from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.recognition.images import ImageError, decode_image, to_jpeg_bytes
from app.schemas import PrepareResponse

router = APIRouter()


@router.post("/images/prepare", response_model=PrepareResponse)
async def prepare_image(request: Request, image: UploadFile) -> PrepareResponse:
    settings = request.app.state.settings
    data = await image.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload is too large")
    try:
        decoded = decode_image(data, settings.max_image_pixels)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    jpeg = to_jpeg_bytes(decoded.image)
    width, height = decoded.image.size
    return PrepareResponse(
        width=width,
        height=height,
        image_base64=base64.b64encode(jpeg).decode("ascii"),
        converted=decoded.converted or decoded.format_name != "JPEG",
    )

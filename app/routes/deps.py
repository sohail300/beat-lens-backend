"""Shared helpers for the API routers."""
import os
import uuid

from fastapi import HTTPException, UploadFile

from app.config import MAX_UPLOAD_BYTES
from app.utils.helpers import create_folder, delete_file

UPLOAD_CHUNK_SIZE = 1024 * 1024


async def save_upload(file: UploadFile, directory: str) -> str:
    """Stream an uploaded file to disk under a random name, enforcing the size limit."""
    create_folder(directory)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext.isascii() or not ext[1:].isalnum():
        ext = ""
    path = os.path.join(directory, f"{uuid.uuid4().hex}{ext}")

    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    )
                out.write(chunk)
    except BaseException:
        delete_file(path)
        raise

    if size == 0:
        delete_file(path)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return path

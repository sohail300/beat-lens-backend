"""Song recognition endpoints."""
from typing import Dict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import MAX_SAMPLE_FINGERPRINTS, TMP_DIR
from app.core.matching import confident_match, find_matches_fgp
from app.db.session import db_dependency
from app.models.schemas import FindRequest
from app.routes.deps import save_upload
from app.services.audio import sample_fingerprint
from app.utils.helpers import delete_file
from app.utils.limits import recognition_limiter, recognition_slots
from app.utils.logger import logger


def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not recognition_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Too many requests, please slow down")


router = APIRouter(prefix="/recognition", tags=["recognition"], dependencies=[Depends(rate_limit)])


def _fingerprint_upload(path: str) -> Dict[int, int]:
    with recognition_slots:
        return sample_fingerprint(path)


def _search(db, fingerprint: Dict[int, int]) -> dict:
    try:
        matches, search_duration = find_matches_fgp(db, fingerprint)
    except Exception as e:
        logger.error(f"Error finding matches: {e}")
        raise HTTPException(status_code=500, detail="Failed to search for matches")

    return {
        "matches": [match.model_dump() for match in confident_match(matches)],
        "search_duration": search_duration,
    }


@router.post("/identify")
async def identify(db: db_dependency, file: UploadFile = File(...)):
    """
    Identify a song from an uploaded or recorded audio clip (only the first 20 s are used).
    `matches` holds the identified song, or is empty if nothing matched confidently.
    """
    path = await save_upload(file, TMP_DIR)
    try:
        fingerprint_dict = await run_in_threadpool(_fingerprint_upload, path)
    except RuntimeError as e:
        logger.info(f"Could not decode upload {file.filename!r}: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file")
    finally:
        delete_file(path)

    if not fingerprint_dict:
        raise HTTPException(status_code=400, detail="Audio clip is too short or silent")

    return await run_in_threadpool(_search, db, fingerprint_dict)


@router.post("/find")
def find_matches(request: FindRequest, db: db_dependency):
    """Find matches for a fingerprint computed by the client. Same response as /identify."""
    if not request.fingerprint:
        raise HTTPException(status_code=400, detail="Fingerprint is empty")
    if len(request.fingerprint) > MAX_SAMPLE_FINGERPRINTS:
        raise HTTPException(status_code=413, detail=f"Fingerprint has more than {MAX_SAMPLE_FINGERPRINTS} entries")
    return _search(db, request.fingerprint)

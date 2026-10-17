"""
WebSocket endpoint.

Clients send JSON messages of the form {"event": "<name>", "data": <payload>}
and receive replies in the same shape:

- totalSongs                         -> {"event": "totalSongs", "data": <int>}
- newRecording   (RecordData)        -> {"event": "matches", "data": [Match] or []}
- newFingerprint ({"fingerprint"})   -> {"event": "matches", "data": [Match] or []}

Recognition events share the HTTP rate limit, and recordings are cut to the first 20 s.

Failures are reported as {"event": "error", "data": {"message": ...}}.
"""
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.config import MAX_CLIP_SECONDS, MAX_SAMPLE_FINGERPRINTS
from app.core.matching import confident_match, find_matches_fgp
from app.db.session import SessionLocal
from app.models.schemas import RecordData
from app.services.audio import fingerprint_samples, process_recording
from app.services.db_service import total_songs
from app.utils.limits import recognition_limiter, recognition_slots
from app.utils.logger import logger

RECOGNITION_EVENTS = {"newRecording", "newFingerprint"}


def _parse(payload: Any) -> dict:
    """Payloads may arrive either as JSON objects or as JSON-encoded strings."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


async def send(websocket: WebSocket, event: str, data: Any) -> None:
    await websocket.send_text(json.dumps({"event": event, "data": data}))


def _match(fingerprint: dict[int, int]) -> list[dict]:
    db = SessionLocal()
    try:
        matches, _ = find_matches_fgp(db, fingerprint)
        return [match.model_dump() for match in confident_match(matches)]
    finally:
        db.close()


def _total_songs() -> int:
    db = SessionLocal()
    try:
        return total_songs(db)
    finally:
        db.close()


async def handle_total_songs(websocket: WebSocket, _payload: Any):
    """Handle totalSongs event."""
    await send(websocket, "totalSongs", await run_in_threadpool(_total_songs))


def _identify_recording(rec_data: RecordData) -> list[dict]:
    with recognition_slots:
        wav_info = process_recording(rec_data.model_dump())
        samples = wav_info.left_channel_samples[:MAX_CLIP_SECONDS * wav_info.sample_rate]
        fingerprints = fingerprint_samples(samples, wav_info.sample_rate, 0)
    return _match({address: couple.anchor_time_ms for address, couple in fingerprints.items()})


async def handle_new_recording(websocket: WebSocket, payload: Any):
    """Handle newRecording event: raw base64 PCM audio -> matches."""
    rec_data = RecordData(**_parse(payload))
    await send(websocket, "matches", await run_in_threadpool(_identify_recording, rec_data))


async def handle_new_fingerprint(websocket: WebSocket, payload: Any):
    """Handle newFingerprint event."""
    fingerprint = _parse(payload).get("fingerprint", {})
    if len(fingerprint) > MAX_SAMPLE_FINGERPRINTS:
        raise ValueError(f"Fingerprint has more than {MAX_SAMPLE_FINGERPRINTS} entries")
    fingerprint_dict = {int(k): int(v) for k, v in fingerprint.items()}
    await send(websocket, "matches", await run_in_threadpool(_match, fingerprint_dict))


HANDLERS = {
    "totalSongs": handle_total_songs,
    "newRecording": handle_new_recording,
    "newFingerprint": handle_new_fingerprint,
}


async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint."""
    await websocket.accept()
    logger.info(f"WebSocket connected: {websocket.client}")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = _parse(data)
                event = message.get("event")
                handler = HANDLERS.get(event)
                if handler is None:
                    raise ValueError(f"Unknown event: {event}")
                client = websocket.client.host if websocket.client else "unknown"
                if event in RECOGNITION_EVENTS and not recognition_limiter.allow(client):
                    raise ValueError("Too many requests, please slow down")
                await handler(websocket, message.get("data", ""))
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.warning(f"WebSocket event failed: {e}")
                await send(websocket, "error", {"message": str(e)[:200]})
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {websocket.client}")

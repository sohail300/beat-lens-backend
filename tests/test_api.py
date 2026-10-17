"""HTTP API and WebSocket."""
import base64
import json

import numpy as np

from tests.conftest import SAMPLE_RATE, encode_webm, write_wav


def _clip(samples, start_s, seconds, noise=0.05, seed=9):
    clip = samples[int(start_s * SAMPLE_RATE):int((start_s + seconds) * SAMPLE_RATE)]
    return clip + noise * np.random.default_rng(seed).standard_normal(len(clip))


def test_health_reports_database(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_identify_browser_recording(client, library_songs, workdir):
    song_id, samples = library_songs["Song A"]
    webm = encode_webm(write_wav(str(workdir / "rec.wav"), _clip(samples, 8, 10)))
    r = client.post("/api/recognition/identify", files={"file": ("rec.webm", open(webm, "rb"), "audio/webm")})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert [m["song_id"] for m in matches] == [song_id]
    assert matches[0]["youtube_id"] == "yt_SongA"


def test_identify_unknown_audio_returns_no_match(client, library_songs, workdir):
    noise = np.random.default_rng(5).standard_normal(10 * SAMPLE_RATE) * 0.3
    path = write_wav(str(workdir / "noise.wav"), noise)
    r = client.post("/api/recognition/identify", files={"file": ("noise.wav", open(path, "rb"))})
    assert r.status_code == 200
    assert r.json()["matches"] == []


def test_identify_rejects_bad_uploads(client):
    r = client.post("/api/recognition/identify", files={"file": ("x.mp3", b"definitely not audio")})
    assert r.status_code == 400 and r.json()["detail"] == "Could not read audio file"
    r = client.post("/api/recognition/identify", files={"file": ("x.wav", b"")})
    assert r.status_code == 400 and r.json()["detail"] == "Uploaded file is empty"


def test_identify_rejects_oversized_upload(client, monkeypatch):
    import app.routes.deps as deps
    monkeypatch.setattr(deps, "MAX_UPLOAD_BYTES", 1000)
    r = client.post("/api/recognition/identify", files={"file": ("big.wav", b"\0" * 5000)})
    assert r.status_code == 413


def test_find_rejects_huge_fingerprint(client, monkeypatch):
    import app.routes.recognition as recognition
    monkeypatch.setattr(recognition, "MAX_SAMPLE_FINGERPRINTS", 10)
    r = client.post("/api/recognition/find", json={"fingerprint": {str(i): 0 for i in range(11)}})
    assert r.status_code == 413


def test_recognition_is_rate_limited(client, monkeypatch):
    from app.utils.limits import RateLimiter
    import app.routes.recognition as recognition
    monkeypatch.setattr(recognition, "recognition_limiter", RateLimiter(2))
    codes = [client.post("/api/recognition/find", json={"fingerprint": {"1": 0}}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_song_listing_detail_and_search(client, library_songs):
    page = client.get("/api/songs", params={"limit": 1}).json()
    assert page["total"] == 2 and [s["title"] for s in page["items"]] == ["Song A"]

    song_id, _ = library_songs["Song B"]
    detail = client.get(f"/api/songs/{song_id}").json()
    assert detail["title"] == "Song B" and detail["fingerprint_count"] > 0
    assert detail["youtube_url"] == "https://www.youtube.com/watch?v=yt_SongB"

    assert client.get("/api/songs/1").status_code == 404
    assert client.get("/api/songs/total").json() == {"total": 2}
    assert [s["title"] for s in client.get("/api/songs", params={"search": "song b"}).json()["items"]] == ["Song B"]
    # LIKE wildcards in the search text are matched literally
    assert client.get("/api/songs", params={"search": "%"}).json()["total"] == 0


def test_no_write_routes_are_exposed(client):
    for method, path in [("POST", "/api/admin/songs"), ("DELETE", "/api/admin/songs"), ("POST", "/api/songs")]:
        assert client.request(method, path).status_code in (404, 405)


def test_websocket_recognition(client, library_songs):
    song_id, samples = library_songs["Song B"]
    pcm = (np.clip(_clip(samples, 5, 10), -1, 1) * 32767).astype(np.int16).tobytes()
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"event": "totalSongs"}))
        assert json.loads(ws.receive_text()) == {"event": "totalSongs", "data": 2}

        ws.send_text(json.dumps({"event": "newRecording", "data": {
            "audio": base64.b64encode(pcm).decode(), "duration": 10, "channels": 1,
            "sample_rate": SAMPLE_RATE, "sample_size": 16,
        }}))
        reply = json.loads(ws.receive_text())
        assert reply["event"] == "matches" and [m["song_id"] for m in reply["data"]] == [song_id]

        ws.send_text("not json")
        assert json.loads(ws.receive_text())["event"] == "error"
        ws.send_text(json.dumps({"event": "newDownload", "data": "https://open.spotify.com/track/x"}))
        assert json.loads(ws.receive_text()) == {"event": "error", "data": {"message": "Unknown event: newDownload"}}


def test_uploads_are_cleaned_up(client, library_songs, workdir):
    import os
    from app.config import TMP_DIR
    path = write_wav(str(workdir / "q.wav"), _clip(library_songs["Song A"][1], 1, 5))
    client.post("/api/recognition/identify", files={"file": ("q.wav", open(path, "rb"))})
    assert os.listdir(TMP_DIR) == []

"""
Test setup. Uses a throwaway SQLite database by default; set TEST_DB_URL to run against Postgres:
    TEST_DB_URL=postgresql://postgres:test@localhost:5432/beat_lens_test pytest
Requires ffmpeg on PATH.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import pytest
import soundfile as sf

# Configure the app before it's imported anywhere
_WORK_DIR = tempfile.mkdtemp(prefix="beat-lens-tests-")
os.environ["DB_URL"] = os.getenv("TEST_DB_URL") or f"sqlite:///{os.path.join(_WORK_DIR, 'test.db')}"
os.environ["ENV"] = "test"
os.environ["SONGS_DIR"] = os.path.join(_WORK_DIR, "songs")
os.environ["TMP_DIR"] = os.path.join(_WORK_DIR, "tmp")
os.environ["RECORDINGS_DIR"] = os.path.join(_WORK_DIR, "recordings")
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["LOG_LEVEL"] = "WARNING"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_RATE = 44100


def make_song(seed: int, seconds: float = 30.0) -> np.ndarray:
    """Synthetic 'song': a random melody of chords, distinct for each seed."""
    rng = np.random.default_rng(seed)
    note = np.arange(SAMPLE_RATE // 4) / SAMPLE_RATE
    notes = []
    for _ in range(int(seconds * 4)):
        f = rng.uniform(200, 2500)
        notes.append(0.4 * np.sin(2 * np.pi * f * note) + 0.2 * np.sin(2 * np.pi * f * 1.26 * note)
                     + 0.1 * np.sin(2 * np.pi * f * 2.0 * note))
    return np.concatenate(notes)


def write_wav(path: str, samples: np.ndarray) -> str:
    sf.write(path, samples, SAMPLE_RATE)
    return path


def encode_webm(wav_path: str) -> str:
    """Re-encode like a browser MediaRecorder would (Opus in WebM)."""
    out = os.path.splitext(wav_path)[0] + ".webm"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "48k", out], check=True)
    return out


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Build the schema with the real migrations, so they're tested too."""
    from alembic import command
    from app.db.schema import alembic_config
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    command.upgrade(alembic_config(), "head")
    yield
    engine.dispose()


@pytest.fixture
def db():
    from app.db.session import SessionLocal
    from app.services import library

    session = SessionLocal()
    library.erase_all(session, include_files=True)
    yield session
    session.close()


@pytest.fixture(autouse=True)
def fake_youtube(monkeypatch):
    """Never hit YouTube from tests. A song titled "NoYT" is one YouTube can't find."""
    import app.services.library as library

    monkeypatch.setattr(
        library, "get_youtube_id",
        lambda track: None if track.title == "NoYT" else "yt_" + track.title.replace(" ", ""),
    )


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


@pytest.fixture
def library_songs(db, workdir):
    """Two songs in the library; returns {title: (id, samples)}."""
    from app.services import library

    songs = {}
    for seed, title in [(1, "Song A"), (2, "Song B")]:
        samples = make_song(seed)
        path = write_wav(str(workdir / f"{title}.wav"), samples)
        songs[title] = (library.add_file(db, path, title, "Artist").id, samples)
    return songs


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        yield c

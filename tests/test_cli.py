"""Library management command line."""
import os

from app import cli
from app.config import SONGS_DIR
from app.db.models import SongORM
from tests.conftest import make_song, write_wav


def test_add_edit_reindex_delete(db, workdir, capsys):
    path = write_wav(str(workdir / "in.wav"), make_song(4, seconds=10))
    assert cli.main(["add-file", path, "--title", "Tune", "--artist", "Band"]) == 0
    assert os.path.exists(path), "the source file must not be modified"
    song = db.query(SongORM).one()
    assert os.path.exists(os.path.join(SONGS_DIR, "Tune - Band.wav"))

    assert cli.main(["add-file", path, "--title", "Tune", "--artist", "Band"]) == 1  # duplicate
    assert "already exists" in capsys.readouterr().err

    assert cli.main(["edit", str(song.id), "--title", "Tune (Live)"]) == 0
    assert os.path.exists(os.path.join(SONGS_DIR, "Tune (Live) - Band.wav"))

    # Simulate a song indexed by the previous algorithm
    db.query(SongORM).update({"algorithm_version": 1})
    db.commit()
    assert cli.main(["reindex", "--outdated"]) == 0
    db.expire_all()
    assert db.query(SongORM).one().algorithm_version == 2

    assert cli.main(["delete", str(song.id)]) == 0
    assert db.query(SongORM).count() == 0
    assert os.path.exists(os.path.join(SONGS_DIR, "Tune (Live) - Band.wav")), "files are kept by default"


def test_add_file_reads_tags_and_needs_youtube_or_force(db, workdir, capsys):
    import subprocess
    wav = write_wav(str(workdir / "x.wav"), make_song(5, seconds=8))
    mp3 = str(workdir / "x.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-metadata", "title=NoYT", "-metadata", "artist=Z", mp3], check=True)

    assert cli.main(["add-file", mp3]) == 1
    assert "use --force" in capsys.readouterr().err
    assert cli.main(["add-file", mp3, "--force"]) == 0
    assert db.query(SongORM).one().title == "NoYT"


def test_erase_requires_confirmation(db, library_songs):
    assert cli.main(["erase"]) == 1
    assert db.query(SongORM).count() == 2
    assert cli.main(["erase", "--yes"]) == 0
    assert db.query(SongORM).count() == 0


def test_unknown_song_is_an_error(db, capsys):
    assert cli.main(["delete", "123"]) == 1
    assert "not found" in capsys.readouterr().err

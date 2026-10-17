"""Migrations upgrade databases created by the app before migrations existed."""
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db.schema import alembic_config


def test_upgrade_legacy_database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    legacy = create_engine(url)
    with legacy.begin() as conn:
        # Schema as the old create_all produced it: no algorithm_version, no songID index
        conn.execute(text('CREATE TABLE songs (id BIGINT PRIMARY KEY, title VARCHAR NOT NULL, artist VARCHAR NOT NULL, "ytID" VARCHAR, key VARCHAR NOT NULL UNIQUE)'))
        conn.execute(text('CREATE TABLE fingerprints (address BIGINT, "anchorTimeMs" BIGINT, "songID" BIGINT, PRIMARY KEY (address, "anchorTimeMs", "songID"))'))
        conn.execute(text("INSERT INTO songs VALUES (1, 'Old', 'Song', NULL, 'Old---Song')"))

    import app.db.session as session
    monkeypatch.setattr(session, "engine", legacy)
    command.upgrade(alembic_config(), "head")

    insp = inspect(legacy)
    assert "algorithm_version" in {c["name"] for c in insp.get_columns("songs")}
    assert "ix_fingerprints_songID" in {i["name"] for i in insp.get_indexes("fingerprints")}
    with legacy.connect() as conn:
        assert conn.execute(text("SELECT algorithm_version FROM songs")).scalar() == 1
    legacy.dispose()

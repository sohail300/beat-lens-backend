"""
Beat Lens library manager. Adds and maintains songs directly in the database.

Run from the backend folder:
    python -m app.cli add <spotify track/album/playlist URL>
    python -m app.cli add-file <path> [--title T] [--artist A] [--force]
    python -m app.cli list [--search Q] [--limit N] [--offset N]
    python -m app.cli show <id>
    python -m app.cli edit <id> [--title T] [--artist A] [--youtube-id Y]
    python -m app.cli delete <id> [--include-files]
    python -m app.cli reindex <id> | --outdated | --all
    python -m app.cli stats
    python -m app.cli erase --yes [--include-files]

It uses DB_URL from .env, or from the environment, e.g. to manage production:
    DB_URL=postgresql://... python -m app.cli add <url>
"""
import argparse
import logging
import sys

from app.db.schema import require_current_schema
from app.db.session import SessionLocal
from app.services import library
from app.services.db_service import count_fingerprints, list_songs, outdated_song_ids
from app.utils.helpers import song_file_path
from app.utils.logger import logger


def _describe(song) -> str:
    yt = f"  https://youtu.be/{song.ytID}" if song.ytID else ""
    return f"[{song.id}] {song.title} - {song.artist}{yt}"


def cmd_add(args, db):
    total = library.download_from_spotify(args.url)
    print(f"Added {total} song(s).")


def cmd_add_file(args, db):
    failed = 0
    for path in args.paths:
        try:
            song = library.add_file(db, path, args.title, args.artist, args.force)
            print(f"Added {_describe(song)}")
        except ValueError as e:
            failed += 1
            print(f"Skipped {path}: {e}", file=sys.stderr)
    return 1 if failed else 0


def cmd_list(args, db):
    rows, total = list_songs(db, args.limit, args.offset, args.search)
    for song in rows:
        print(_describe(song))
    print(f"-- {len(rows)} of {total} song(s)")


def cmd_show(args, db):
    song = library.get_song_or_raise(db, args.id)
    print(_describe(song))
    print(f"  fingerprints: {count_fingerprints(db, song.id)} (algorithm v{song.algorithm_version})")
    print(f"  audio file:   {song_file_path(song.title, song.artist)}")


def cmd_edit(args, db):
    if args.title is None and args.artist is None and args.youtube_id is None:
        raise ValueError("Nothing to change; pass --title, --artist and/or --youtube-id")
    song = library.edit_song(db, args.id, args.title, args.artist, args.youtube_id)
    print(f"Updated {_describe(song)}")


def cmd_delete(args, db):
    song = library.erase_song(db, args.id, args.include_files)
    print(f"Deleted {_describe(song)}" + (" (and its audio file)" if args.include_files else ""))


def cmd_reindex(args, db):
    if args.all:
        ids = [row.id for row in list_songs(db, limit=10**9, offset=0)[0]]
    elif args.outdated:
        ids = outdated_song_ids(db)
        if not ids:
            print("All songs are up to date.")
    elif args.id is not None:
        ids = [args.id]
    else:
        raise ValueError("Pass a song id, --outdated or --all")

    failed = 0
    for song_id in ids:
        try:
            count = library.reindex_song(db, song_id)
            print(f"Re-indexed {song_id}: {count} fingerprints")
        except (ValueError, LookupError) as e:
            failed += 1
            print(f"Skipped {song_id}: {e}", file=sys.stderr)
    return 1 if failed else 0


def cmd_stats(args, db):
    s = library.stats(db)
    print(f"songs:        {s['songs']} ({s['outdated_songs']} need re-indexing)")
    print(f"fingerprints: {s['fingerprints']}")
    print(f"audio files:  {s['audio_files']} ({s['audio_bytes'] / 1024 / 1024:.1f} MB in {s['songs_dir']})")


def cmd_erase(args, db):
    if not args.yes:
        raise ValueError("This deletes every song and fingerprint; re-run with --yes to confirm")
    library.erase_all(db, args.include_files)
    print("Erased all songs and fingerprints" + (" and audio files" if args.include_files else ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Manage the Beat Lens song library.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="Download and fingerprint a Spotify track, album or playlist")
    p.add_argument("url")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("add-file", help="Fingerprint local audio file(s)")
    p.add_argument("paths", nargs="+")
    p.add_argument("--title", help="Override the title tag (single file only)")
    p.add_argument("--artist", help="Override the artist tag")
    p.add_argument("--force", action="store_true", help="Add even if no YouTube video is found")
    p.set_defaults(func=cmd_add_file)

    p = sub.add_parser("list", help="List songs")
    p.add_argument("--search")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="Show one song")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("edit", help="Change a song's title, artist or YouTube ID")
    p.add_argument("id", type=int)
    p.add_argument("--title")
    p.add_argument("--artist")
    p.add_argument("--youtube-id")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("delete", help="Delete one song and its fingerprints")
    p.add_argument("id", type=int)
    p.add_argument("--include-files", action="store_true", help="Also delete its audio file")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("reindex", help="Recompute fingerprints from the audio files")
    p.add_argument("id", type=int, nargs="?")
    p.add_argument("--all", action="store_true", help="Re-index every song")
    p.add_argument("--outdated", action="store_true", help="Re-index songs made with an older algorithm version")
    p.set_defaults(func=cmd_reindex)

    p = sub.add_parser("stats", help="Show library size")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("erase", help="Delete every song and fingerprint")
    p.add_argument("--yes", action="store_true", help="Confirm")
    p.add_argument("--include-files", action="store_true", help="Also delete all audio files")
    p.set_defaults(func=cmd_erase)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "title", None) and len(getattr(args, "paths", [])) > 1:
        print("--title can only be used with a single file", file=sys.stderr)
        return 2

    # Progress messages only; library debug output is noise on the command line
    logging.getLogger().setLevel(logging.WARNING)
    logger.setLevel(logging.INFO)

    db = SessionLocal()
    try:
        require_current_schema()
        return args.func(args, db) or 0
    except (ValueError, LookupError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

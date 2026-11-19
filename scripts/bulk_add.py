"""
Bulk-add songs from text files of 'Title | Artist [| search hint]' lines.
Run from the backend folder:  python -m scripts.bulk_add scripts/songs_english.txt scripts/songs_indian.txt
Searches YouTube for each song (skipping ones already in the library) and adds the first sensible result.
"""
import concurrent.futures
import sys

import yt_dlp

from app.db.session import SessionLocal
from app.services import library
from app.services.db_service import list_songs

MAX_SECONDS = 600  # skip hour-long mixes / loops


def find_video(query: str):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        res = ydl.extract_info(f"ytsearch5:{query}", download=False)
    for e in (res or {}).get("entries") or []:
        if e and e.get("id") and (e.get("duration") or 0) <= MAX_SECONDS:
            return e["id"]
    return None


def work(item):
    title, artist, hint = item
    db = SessionLocal()
    try:
        vid = find_video(f"{title} {artist} {hint} official audio".replace("  ", " "))
        if not vid:
            return item, "no YouTube result"
        song = library.add_youtube(db, vid, title, artist)
        return item, f"ok [{song.id}] https://youtu.be/{vid}"
    except Exception as e:  # keep going on any single failure
        return item, f"FAILED: {e}"
    finally:
        db.close()


def main(paths):
    items = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 2 and parts[0]:
                items.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))

    db = SessionLocal()
    existing = {(s.title.lower(), s.artist.lower()) for s in list_songs(db, limit=10**9, offset=0)[0]}
    db.close()
    items = [i for i in items if (i[0].lower(), i[1].lower()) not in existing]
    print(f"{len(items)} song(s) to add", flush=True)

    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for (title, artist, _), status in ex.map(work, items):
            failed += status.startswith(("FAILED", "no "))
            print(f"{title} - {artist}: {status}", flush=True)
    print(f"Done. {len(items) - failed} added, {failed} failed.")


if __name__ == "__main__":
    main(sys.argv[1:])

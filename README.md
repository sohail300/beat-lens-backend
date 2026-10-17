# Beat Lens Backend

FastAPI backend for song recognition, converted from the Go-based seek-tune application.

Beat Lens fingerprints audio the way Shazam does: it finds the loudest points in a spectrogram,
hashes pairs of them, and identifies a recording by finding the song whose hashes line up with
the recording's at a consistent time offset.

- **Production server**: read-only. Health check, song recognition (HTTP upload or WebSocket) and song listing.
- **Library CLI** (`app/cli.py`): run on your own machine to add songs (from Spotify links via YouTube, or local files), edit, delete and re-index them in the database.

## Requirements

- Python 3.11+
- FFmpeg on `PATH`
- PostgreSQL 13+ (e.g. [Neon](https://neon.tech))
- For adding songs from Spotify: `yt-dlp` and Spotify API credentials ([getting started guide](https://developer.spotify.com/documentation/web-api/tutorials/getting-started))

## Local Setup

```bash
cd beat-lens-backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env              # then edit DB_URL (and Spotify credentials to add songs)
alembic upgrade head              # create / update the database schema
python -m uvicorn main:app --reload --port 5000
```

Interactive API docs are served at `http://localhost:5000/docs`.
Never commit your real `.env`; `.env.example` must only contain placeholders.

## API

All routes are under `/api` and are read-only.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | `{"status": "ok", "database": "ok"}`, or 503 if the database is unreachable |
| `POST` | `/api/recognition/identify` | Identify a song. Multipart form with a `file` field, any format ffmpeg can read (e.g. a browser `webm` recording). Only the first 20 s are used |
| `POST` | `/api/recognition/find` | Same, for a client-computed fingerprint: `{"fingerprint": {"<address>": <anchor_time_ms>}}` |
| `GET` | `/api/songs` | List songs alphabetically. Query: `search` (title/artist), `limit` (1-100, default 20), `offset` |
| `GET` | `/api/songs/total` | Total song count |
| `GET` | `/api/songs/{id}` | One song, with its fingerprint count |

Recognition returns the identified song, or an empty list when nothing matched confidently:
```json
{
  "matches": [
    {"song_id": 1, "song_title": "...", "song_artist": "...", "youtube_id": "...", "timestamp": 12000, "score": 48.0}
  ],
  "search_duration": 0.01
}
```

Errors: 400 (unreadable, empty or silent audio), 413 (upload over `MAX_UPLOAD_MB`, or too many fingerprints), 429 (rate limited).

### WebSocket

Connect to `/ws` and send `{"event": "<name>", "data": <payload>}`. Replies use the same shape.

| Event sent | Payload | Reply event |
|---|---|---|
| `totalSongs` | none | `totalSongs` (number) |
| `newRecording` | `{"audio": <base64 16-bit PCM>, "duration", "channels", "sample_rate", "sample_size": 16}` | `matches` (the song, or `[]`) |
| `newFingerprint` | `{"fingerprint": {...}}` | `matches` (the song, or `[]`) |

Errors come back as `{"event": "error", "data": {"message": "..."}}`; the connection stays open.

### How matching decides

Every sample shares a few hashes with unrelated songs by chance, so the best-scoring song is only
reported if its score is at least `MIN_MATCH_SCORE` (10) **and** at least `MIN_MATCH_RATIO` (2.5×)
the runner-up's. Tested on real music with clean, noisy (down to 0 dB SNR), low-bitrate Opus and
phone-band clips, including unknown songs by the same composer as library songs:

| Clip length | Songs found | False matches |
|---|---|---|
| 5 s | ~87% | 0 |
| 10 s | ~93% | 0 |
| 20 s | ~98% | 0 |

**Clients should record 10-20 seconds.** Both thresholds can be tuned through environment variables.

## Managing the Song Library

Songs are added, edited and removed with `app/cli.py`, run from the backend folder on your own machine.
Nothing on the server can modify the library.

```bash
python -m app.cli add <spotify track/album/playlist URL>   # find on YouTube, download, fingerprint
python -m app.cli add-file song.mp3 other.flac             # fingerprint local files (tags give title/artist)
python -m app.cli add-file clip.wav --title "T" --artist "A" [--force]
python -m app.cli list [--search queen] [--limit 50] [--offset 0]
python -m app.cli show <id>
python -m app.cli edit <id> [--title T] [--artist A] [--youtube-id Y]
python -m app.cli delete <id> [--include-files]
python -m app.cli reindex <id> | --outdated | --all
python -m app.cli stats
python -m app.cli erase --yes [--include-files]
```

It uses `DB_URL` from `.env`. To manage the production library, point it at the production database:
```bash
DB_URL='postgresql://...' python -m app.cli add <url>
```

`add` needs `yt-dlp` and the Spotify credentials. YouTube often blocks downloads from cloud servers, which is another reason this runs locally.

### Storage

The server never stores songs; recognition only needs the fingerprints in the database.
Songs you add keep their audio on your machine in `songs/` (override with `SONGS_DIR`) as `<Title> - <Artist>.wav`,
so `reindex` and `edit` can use them later. Set `KEEP_AUDIO=false` to discard audio after fingerprinting.
`tmp/` holds uploads while they're processed; leftovers older than an hour are deleted automatically.

**Database size**: about 115 bytes per fingerprint, roughly 0.3-1 MB per song (measured on Postgres 17,
indexes included). Check yours with `python -m app.cli stats`.

### Fingerprint algorithm versions

Each song records the algorithm version it was fingerprinted with (`ALGORITHM_VERSION` in
`app/core/fingerprinting.py`). After the algorithm changes, old songs no longer match new recordings:
re-index them with `python -m app.cli reindex --outdated` (needs their audio in `songs/`), or delete and re-add them.
Songs added before version 2 must be re-indexed or re-added.

## Database Migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/); the server and CLI refuse to start until it's up to date.

```bash
alembic upgrade head                      # apply migrations (safe on databases created before migrations existed)
alembic revision -m "describe the change" # create a new migration in migrations/versions/
```

## Deployment

The `Dockerfile` builds a production image (Python 3.12, ffmpeg, non-root user, health check, multiple workers):

```bash
docker build -t beat-lens-backend .
docker run -p 5000:5000 --env-file .env -e ENV=production beat-lens-backend
```

Set at least `DB_URL`, `ENV=production` and `CORS_ORIGINS` (your frontend's URL). Then:

1. **Migrations**: run `alembic upgrade head` as a one-off release / pre-deploy command, or set `RUN_MIGRATIONS=true` when only one instance starts at a time.
2. **Workers**: `WEB_CONCURRENCY` (default 2) sets the number of processes; fingerprinting is CPU-bound, so about one per CPU core.
3. **Rate limiting** is per worker and per client IP (`RATE_LIMIT_PER_MINUTE`, default 30). Behind a load balancer the real client IP is taken from `X-Forwarded-For`; restrict `FORWARDED_ALLOW_IPS` to your proxy's address if the platform documents it.
4. **Neon**: use the pooled connection string. Idle connections are checked before use.
5. **Errors**: set `SENTRY_DSN` to report unhandled errors to Sentry.

Spotify credentials are not needed on the server.

## Tests

```bash
pytest                                                           # SQLite, needs ffmpeg
TEST_DB_URL=postgresql://user:pass@localhost:5432/test pytest    # against Postgres
```

CI (`.github/workflows/ci.yml`) runs the tests against Postgres and builds the Docker image on every push and pull request.

## Project Structure

```
main.py                  # FastAPI app entry point
app/
├── cli.py               # Song library management (command line)
├── config.py            # Configuration (environment variables)
├── core/                # Spectrogram, fingerprinting and matching
├── db/                  # SQLAlchemy models, session, schema check
├── models/              # Pydantic models
├── routes/              # Read-only routers (health, recognition, songs) + WebSocket
├── services/            # Audio conversion, database, library, Spotify, YouTube
└── utils/               # Helpers, logging, rate limits
migrations/              # Alembic migrations
tests/                   # pytest suite
```

## License

This project is licensed under the MIT License.

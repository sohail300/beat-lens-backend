# Beat Lens Backend

FastAPI backend for song recognition, converted from the Go-based seek-tune application.

## Description

Beat Lens Backend is an implementation of Shazam's song recognition algorithm. It integrates with Spotify and YouTube APIs to find and download songs, and provides audio fingerprinting capabilities.

## Features

- Audio fingerprinting using Shazam algorithm
- Song matching and recognition
- Spotify integration (tracks, albums, playlists)
- YouTube audio downloading
- WebSocket support for real-time communication
- Database support (PostgreSQL)

## Installation

### Prerequisites

- Python 3.11+
- FFmpeg
- yt-dlp
- PostgreSQL 13+ (running instance)

### Steps

1. Clone the repository and navigate to the backend:
```bash
cd beat-lens-backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

### Spotify API Setup

1. Get credentials: Follow the [official getting started guide](https://developer.spotify.com/documentation/web-api/tutorials/getting-started) to create a Spotify app and obtain your **Client ID** and **Client Secret**.

2. Configure: Update `.env` file:
```bash
SPOTIFY_CLIENT_ID=your-client-id
SPOTIFY_CLIENT_SECRET=your-client-secret
```

## Usage

### Start the Server

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

Or using the main module:
```bash
python -m app.main
```

### API Endpoints

- `GET /api/health` - Health check
- `GET /api/songs/total` - Get total song count
- `POST /api/find` - Find matches for audio file
- `POST /api/download` - Download from Spotify URL
- `POST /api/save` - Save local audio file to database
- `DELETE /api/erase` - Clear database/files

### WebSocket

Connect to `/socket.io/` for real-time events:
- `totalSongs` - Get total song count
- `newDownload` - Download from Spotify URL
- `newRecording` - Handle audio recording
- `newFingerprint` - Find matches for fingerprint

## Database

This application now uses **PostgreSQL** exclusively.

### PostgreSQL Configuration

1. Install PostgreSQL and create a database/user, for example:
```bash
createdb beat_lens
createuser beat_lens --pwprompt
```

2. Configure in `.env` using a single `DB_URL`:
```bash
DB_URL=postgresql://beat_lens:your-password@localhost:5432/beat_lens
```

**Format:** `postgresql://username:password@host:port/database_name`

**Example for local development:**
```bash
DB_URL=postgresql://beat_lens:beat_lens@localhost:5432/beat_lens
```

**Note:** For backward compatibility, you can still use individual `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASS` variables if `DB_URL` is not set.

## Docker

### Build and Run

```bash
docker build -t beat-lens-backend .
docker run -p 5000:5000 --env-file .env beat-lens-backend
```

## Development

The application structure:
```
app/
├── main.py              # FastAPI app entry point
├── config.py            # Configuration
├── models/              # Pydantic models
├── api/                 # REST and WebSocket endpoints
├── core/                # Audio processing algorithms
├── services/            # Business logic services
├── utils/               # Utility functions
└── db/                  # Database clients
```

## License

This project is licensed under the MIT License.


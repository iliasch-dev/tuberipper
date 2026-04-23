<img width="128" height="128" alt="image" src="https://github.com/user-attachments/assets/919c7d97-831c-4b2f-8163-8cef67cd18b3" />

# Tuberipper

Tuberipper monitors a list of YouTube channels and automatically downloads their latest videos or livestreams as MP3 files. It uses Selenium to navigate YouTube, `yt-dlp` to download and extract audio, and PostgreSQL to track what has already been scraped so nothing is downloaded twice. A lightweight web UI lets you manage which channels to watch and whether to scrape their videos, livestreams, or both. Notifications are sent via Pushover when a new rip completes.

## How it works

1. The **scraper** opens YouTube with a stealth Chrome session, checks each configured channel's Videos and/or Streams tab, and grabs the first (newest) item.
2. If the video ID is not already in the database, it downloads the audio with `yt-dlp`, converts it to MP3 at 192 kbps via `ffmpeg`, embeds the thumbnail and metadata with `eyed3`, validates the duration, and moves the file to the output directory.
3. The **web UI** (Flask, port 5000) lets you add or remove channels and toggle livestream / video scraping per channel without touching the database directly.

## Fresh install (Docker)

### Prerequisites

- Docker + Docker Compose
- YouTube session cookies exported as `cookies/youtube_cookies.txt` (Netscape format)  
  Run `./refresh_youtube_cookies.sh` after logging into YouTube in Chrome or Firefox.
- A Pushover account and API token (optional — edit `scraper/utils.py` to disable notifications)

### 1 — Clone and create config.json

```bash
git clone <repo-url>
cd tuberipper
```

Create `config.json` in the project root (it is gitignored):

```json
{
  "DB_NAME": "tuberip",
  "DB_USER": "postgres",
  "DB_PASS": "changeme",
  "DB_HOST": "db",
  "CHROMEDRIVER_PATH": "",
  "WEBDRIVER_TIMEOUT": "30",
  "COOKIES_PATH": "cookies/",
  "SCREENCAP_PATH": "screencap/",
  "RIPS_PATH": "/tmp/tuberipper/",
  "YOUTUBE_URL": "https://www.youtube.com/"
}
```

> `DB_HOST` must be `"db"` (the Docker service name) and `CHROMEDRIVER_PATH` must be `""` so the system-installed driver is used.

### 2 — Set your database password

The password in `config.json` (`DB_PASS`) must match `POSTGRES_PASSWORD` in `docker-compose.yml`. Change `changeme` in both to the same value.

### 3 — Export YouTube cookies

```bash
./refresh_youtube_cookies.sh
```

This creates `cookies/youtube_cookies.txt`. Re-run whenever yt-dlp starts reporting authentication errors.

### 4 — Build and start

```bash
docker compose up -d --build
```

| Service | Purpose | Port |
|---------|---------|------|
| `db` | PostgreSQL database | internal |
| `webapp` | Channel management UI | 5000 |
| `scraper` | YouTube scraper | — |

Open **http://localhost:5000** to add channels before the scraper's first run.

### 5 — Add channels via the web UI

Navigate to `http://localhost:5000`, enter a channel handle (e.g. `@MrBeast`) or channel ID, and toggle whether to scrape **Videos**, **Livestreams**, or both.

### 6 — Output

Downloaded MP3s land in the `rips` Docker volume (mapped to `/media/chronalis/tuberipper` inside the scraper container). To use a host directory instead, replace the volume reference in `docker-compose.yml`:

```yaml
volumes:
  - /your/local/path:/media/chronalis/tuberipper
```

## Running without Docker

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

System dependencies required: `chromium`, `chromium-driver`, `ffmpeg`, `deno`.

```bash
python -m scraper.main
```

The scraper is designed to be run as a cron job. Example — every hour:

```
0 * * * * cd /path/to/tuberipper && ./venv/bin/python -m scraper.main >> tuberipper.log 2>&1
```

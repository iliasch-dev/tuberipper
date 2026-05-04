<div style="display:flex;justify-content:center;align-items:center;height:100vh;">
  <img width="128" height="128" alt="image" src="https://github.com/user-attachments/assets/919c7d97-831c-4b2f-8163-8cef67cd18b3" />
</div>

Tuberipper monitors a list of YouTube channels and automatically downloads their latest videos or livestreams as MP3 files. It uses Selenium to navigate YouTube, `yt-dlp` to download and extract audio, and PostgreSQL to track what has already been scraped so nothing is downloaded twice. A lightweight web UI lets you manage channels, toggle scraping preferences, and configure the run schedule. Notifications are sent via Pushover when a new rip completes. You may used it along with a web app player like Audiobookshelf.

## How it works

1. The **scraper** runs continuously on a configurable schedule. On each tick it opens YouTube with a stealth Chrome session, checks each configured channel's Videos and/or Streams tab, and grabs the first (newest) item.
2. If the video ID is not already in the database, it downloads the audio with `yt-dlp`, converts it to MP3 at 192 kbps via `ffmpeg`, embeds the thumbnail and metadata with `eyed3`, validates the duration, and moves the file to the output directory.
3. The **web UI** (Flask, port 5002) lets you add or remove channels, toggle livestream / video scraping per channel, set the scraper interval, and view a live stats dashboard (next run time, total runs, videos ripped, error count) and a colour-coded live log viewer — all without touching the database or restarting containers. Access is protected by a username/password login page.

## Fresh install (Docker)

### Prerequisites

- Docker + Docker Compose
- YouTube session cookies exported as `cookies/youtube_cookies.txt` (Netscape format) — run `./refresh_youtube_cookies.sh` after logging into YouTube in Chrome or Firefox
- A Pushover account and API token (optional — edit `scraper/utils.py` to disable notifications)

> `cookies/` and `logs/` are gitignored and created at runtime — do not commit them.

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
  "DB_PASS": "your-password",
  "DB_HOST": "db",
  "CHROMEDRIVER_PATH": "",
  "WEBDRIVER_TIMEOUT": "30",
  "COOKIES_PATH": "cookies/",
  "SCREENCAP_PATH": "screencap/",
  "RIPS_PATH": "/media/chronalis/tuberipper/",
  "YOUTUBE_URL": "https://www.youtube.com/",
  "PUSHOVER_API_TOKEN": "your-pushover-app-token",
  "PUSHOVER_USER_KEY": "your-pushover-user-key"
}
```

> Pushover credentials are optional — if omitted, notifications are silently skipped.

> `DB_HOST` must be `"db"` (the Docker service name) and `CHROMEDRIVER_PATH` must be `""` so the system-installed driver is used.

### 2 — Set passwords

- `DB_PASS` in `config.json` must match `POSTGRES_PASSWORD` in `docker-compose.yml`
- Set `SECRET_KEY` in `docker-compose.yml` to a random string (used for Flask session signing)
- Set `WEBAPP_USERNAME` and `WEBAPP_PASSWORD` in `docker-compose.yml` to protect the web UI with a login page. Leave both empty to disable auth.

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
| `webapp` | Channel management UI | 5002 |
| `scraper` | YouTube scraper (long-running) | — |

### 5 — Configure via the web UI

Open **http://localhost:5002** and log in with the credentials set in `docker-compose.yml`, then:
- Add channels by handle (e.g. `@MrBeast`) or channel ID, toggling **Videos** and/or **Livestreams**
- Set the scrape **interval** using the scheduler card (presets: 30m, 1h, 2h, 6h, 12h, 24h) and enable/disable the scheduler
- Monitor the dashboard stats (next run, total runs, videos ripped, errors) and the live log viewer

The scraper runs immediately on startup, then repeats on the configured interval. Schedule changes take effect after the current run finishes — no restart needed.

To rebuild and restart only the webapp container (e.g. after a code change), run:

```bash
./webapp/restart.sh
```

### 6 — Output

Downloaded MP3s land in the `rips` Docker volume (mapped to `/media/chronalis/tuberipper` inside the scraper container). To use a host directory instead, replace the volume reference in `docker-compose.yml`:

```yaml
volumes:
  - /your/local/path:/media/chronalis/tuberipper
```

Scraper logs are written to `./logs/tuberipper.log` on the host (bind-mounted into both the scraper and webapp containers) and streamed live in the web UI.

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

The scraper will run on the interval configured in the database (default 60 minutes). The web UI must be running for schedule changes to take effect.

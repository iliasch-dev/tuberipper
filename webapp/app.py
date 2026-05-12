from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context, session
import psycopg2
import subprocess
import os
import secrets
from functools import wraps
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_TZ = ZoneInfo('Europe/Athens')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

_WEBAPP_USERNAME = os.environ.get('WEBAPP_USERNAME', '')
_WEBAPP_PASSWORD = os.environ.get('WEBAPP_PASSWORD', '')
_LOG_PATH = os.environ.get('LOG_PATH', 'tuberipper.log')

_AUTH_ENABLED = bool(_WEBAPP_USERNAME and _WEBAPP_PASSWORD)


def _require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if _AUTH_ENABLED and not session.get('logged_in'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


def get_db():
    return psycopg2.connect(
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASS'],
        host=os.environ['DB_HOST'],
        port=os.environ.get('DB_PORT', '5432'),
    )


def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rips (
            id SERIAL PRIMARY KEY,
            creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            channel TEXT,
            video_title TEXT,
            duration INTEGER,
            format TEXT CHECK(format IN ('VIDEO', 'AUDIO')),
            type TEXT CHECK(type IN ('STREAM', 'VIDEO')),
            thumbnail_image_url TEXT,
            video_id TEXT,
            extracted_audio_filename TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id SERIAL PRIMARY KEY,
            channel TEXT NOT NULL,
            scrap_streams BOOLEAN NOT NULL DEFAULT FALSE,
            scrap_videos BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY DEFAULT 1,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            run_count INTEGER NOT NULL DEFAULT 0,
            last_run_at TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS run_count INTEGER NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP")
    cur.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP")
    cur.execute("""
        INSERT INTO schedule (id, interval_minutes, enabled) VALUES (1, 60, TRUE)
        ON CONFLICT (id) DO NOTHING
    """)
    conn.commit()
    cur.close()
    conn.close()


def _count_log_errors():
    count = 0
    today = datetime.now(_TZ).strftime('%Y-%m-%d')
    try:
        if os.path.exists(_LOG_PATH):
            with open(_LOG_PATH, 'r', errors='ignore') as f:
                for line in f:
                    if line.startswith(today) and ' ERROR' in line:
                        count += 1
    except OSError:
        pass
    return count


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not _AUTH_ENABLED:
        return redirect(url_for('index'))
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        username_ok = secrets.compare_digest(username, _WEBAPP_USERNAME)
        password_ok = secrets.compare_digest(password, _WEBAPP_PASSWORD)
        if username_ok and password_ok:
            session['logged_in'] = True
            session.permanent = False
            return redirect(request.args.get('next') or url_for('index'))
        error = 'Invalid credentials.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@_require_login
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, channel, scrap_streams, scrap_videos FROM channels ORDER BY id")
    channels = cur.fetchall()
    cur.execute("SELECT interval_minutes, enabled, run_count, last_run_at, next_run_at FROM schedule WHERE id = 1")
    schedule = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM rips")
    total_rips = cur.fetchone()[0]
    cur.execute("""
        SELECT extracted_audio_filename, channel, creation_date
        FROM rips ORDER BY creation_date DESC LIMIT 10
    """)
    latest_rips = cur.fetchall()
    cur.close()
    conn.close()

    next_fire = None
    if schedule and schedule[1]:
        nf_utc = None
        if schedule[4]:
            nf_utc = schedule[4].replace(tzinfo=timezone.utc)
        elif schedule[3]:
            nf_utc = schedule[3].replace(tzinfo=timezone.utc) + timedelta(minutes=schedule[0])
        if nf_utc:
            next_fire = nf_utc.astimezone(_TZ).strftime('%d-%m-%Y %H:%M:%S')


    stats = {
        'next_fire': next_fire or ('Disabled' if schedule and not schedule[1] else 'Pending'),
        'run_count': schedule[2] if schedule else 0,
        'total_rips': total_rips,
        'error_count': _count_log_errors(),
    }

    latest_rips_fmt = [
        (filename, channel, dt.replace(tzinfo=timezone.utc).astimezone(_TZ).strftime('%d-%m-%Y %H:%M:%S'))
        for filename, channel, dt in latest_rips if dt
    ]

    return render_template('index.html', channels=channels, schedule=schedule, stats=stats, latest_rips=latest_rips_fmt)


@app.route('/api/stats')
@_require_login
def api_stats():
    from flask import jsonify
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT interval_minutes, enabled, run_count, last_run_at, next_run_at FROM schedule WHERE id = 1")
    schedule = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM rips")
    total_rips = cur.fetchone()[0]
    cur.execute("""
        SELECT extracted_audio_filename, channel, creation_date
        FROM rips ORDER BY creation_date DESC LIMIT 10
    """)
    latest_rips = cur.fetchall()
    cur.close()
    conn.close()

    next_fire = None
    if schedule and schedule[1]:
        nf_utc = None
        if schedule[4]:
            nf_utc = schedule[4].replace(tzinfo=timezone.utc)
        elif schedule[3]:
            nf_utc = schedule[3].replace(tzinfo=timezone.utc) + timedelta(minutes=schedule[0])
        if nf_utc:
            next_fire = nf_utc.astimezone(_TZ).strftime('%d-%m-%Y %H:%M:%S')

    return jsonify({
        'stats': {
            'next_fire': next_fire or ('Disabled' if schedule and not schedule[1] else 'Pending'),
            'run_count': schedule[2] if schedule else 0,
            'total_rips': total_rips,
            'error_count': _count_log_errors(),
        },
        'latest_rips': [
            {'filename': filename, 'channel': channel,
             'date': dt.replace(tzinfo=timezone.utc).astimezone(_TZ).strftime('%d-%m-%Y %H:%M:%S')}
            for filename, channel, dt in latest_rips if dt
        ]
    })


@app.route('/add', methods=['POST'])
@_require_login
def add_channel():
    channel = request.form.get('channel', '').strip()
    if not channel:
        flash('Channel name cannot be empty.', 'error')
        return redirect(url_for('index'))
    scrap_streams = 'scrap_streams' in request.form
    scrap_videos = 'scrap_videos' in request.form
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO channels (channel, scrap_streams, scrap_videos) VALUES (%s, %s, %s)",
        (channel, scrap_streams, scrap_videos),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))


@app.route('/update/<int:channel_id>', methods=['POST'])
@_require_login
def update_channel(channel_id):
    scrap_streams = 'scrap_streams' in request.form
    scrap_videos = 'scrap_videos' in request.form
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE channels SET scrap_streams = %s, scrap_videos = %s WHERE id = %s",
        (scrap_streams, scrap_videos, channel_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return ('', 204)


@app.route('/delete/<int:channel_id>', methods=['POST'])
@_require_login
def delete_channel(channel_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))


@app.route('/schedule/update', methods=['POST'])
@_require_login
def update_schedule():
    try:
        interval_minutes = int(request.form.get('interval_minutes', 60))
        if not (1 <= interval_minutes <= 10080):
            raise ValueError
    except ValueError:
        flash('Interval must be between 1 and 10080 minutes (1 week max).', 'error')
        return redirect(url_for('index'))
    enabled = 'enabled' in request.form
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO schedule (id, interval_minutes, enabled) VALUES (1, %s, %s)
        ON CONFLICT (id) DO UPDATE SET interval_minutes = EXCLUDED.interval_minutes, enabled = EXCLUDED.enabled
    """, (interval_minutes, enabled))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))


@app.route('/logs/stream')
@_require_login
def stream_logs():
    def generate():
        proc = None
        try:
            if not os.path.exists(_LOG_PATH):
                yield "data: Waiting for scraper to start...\n\n"
            proc = subprocess.Popen(
                ['tail', '-n', '100', '-f', _LOG_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            for line in proc.stdout:
                yield f"data: {line.rstrip()}\n\n"
        except GeneratorExit:
            pass
        finally:
            if proc:
                proc.terminate()

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


if __name__ == '__main__':
    ensure_tables()
    import sys
    sys.path.insert(0, '/app')
    from scraper.main import start_scheduler
    start_scheduler()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

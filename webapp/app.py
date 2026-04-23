from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context
import psycopg2
import subprocess
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tuberipper-dev-secret')


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
    cur.execute("""
        INSERT INTO schedule (id, interval_minutes, enabled) VALUES (1, 60, TRUE)
        ON CONFLICT (id) DO NOTHING
    """)
    conn.commit()
    cur.close()
    conn.close()


def _count_log_errors():
    log_path = os.environ.get('LOG_PATH', 'tuberipper.log')
    count = 0
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', errors='ignore') as f:
                for line in f:
                    if ' ERROR' in line:
                        count += 1
    except OSError:
        pass
    return count


@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, channel, scrap_streams, scrap_videos FROM channels ORDER BY id")
    channels = cur.fetchall()
    cur.execute("SELECT interval_minutes, enabled, run_count, last_run_at FROM schedule WHERE id = 1")
    schedule = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM rips")
    total_rips = cur.fetchone()[0]
    cur.close()
    conn.close()

    next_fire = None
    if schedule and schedule[1] and schedule[3]:
        nf = schedule[3] + timedelta(minutes=schedule[0])
        if nf > datetime.utcnow():
            next_fire = nf.strftime('%H:%M:%S')
        else:
            next_fire = 'Soon'

    stats = {
        'next_fire': next_fire or ('Disabled' if schedule and not schedule[1] else 'Soon'),
        'run_count': schedule[2] if schedule else 0,
        'total_rips': total_rips,
        'error_count': _count_log_errors(),
    }

    return render_template('index.html', channels=channels, schedule=schedule, stats=stats)


@app.route('/add', methods=['POST'])
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
    return redirect(url_for('index'))


@app.route('/delete/<int:channel_id>', methods=['POST'])
def delete_channel(channel_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))


@app.route('/schedule/update', methods=['POST'])
def update_schedule():
    try:
        interval_minutes = int(request.form.get('interval_minutes', 60))
        if interval_minutes < 1:
            raise ValueError
    except ValueError:
        flash('Interval must be a positive number.', 'error')
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
def stream_logs():
    log_path = os.environ.get('LOG_PATH', 'tuberipper.log')

    def generate():
        proc = None
        try:
            if not os.path.exists(log_path):
                yield "data: Waiting for scraper to start...\n\n"
            proc = subprocess.Popen(
                ['tail', '-n', '100', '-f', log_path],
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
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

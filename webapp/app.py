from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
import os

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
            enabled BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)
    cur.execute("""
        INSERT INTO schedule (id, interval_minutes, enabled) VALUES (1, 60, TRUE)
        ON CONFLICT (id) DO NOTHING
    """)
    conn.commit()
    cur.close()
    conn.close()


@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, channel, scrap_streams, scrap_videos FROM channels ORDER BY id")
    channels = cur.fetchall()
    cur.execute("SELECT interval_minutes, enabled FROM schedule WHERE id = 1")
    schedule = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('index.html', channels=channels, schedule=schedule)


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


if __name__ == '__main__':
    ensure_tables()
    app.run(host='0.0.0.0', port=5000, debug=False)

import psycopg2
import logging
import hashlib
from . import utils

config = utils.load_config("config.json")
db_connection_params = {
    "dbname": config['DB_NAME'],
    "user": config['DB_USER'],
    "password": config['DB_PASS'],
    "host": config['DB_HOST'],
    # "port": config['DB_PORT']
}

_rips_table = '''CREATE TABLE IF NOT EXISTS rips
                      (id SERIAL PRIMARY KEY,
                      creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      channel TEXT,
                      video_title TEXT,
                      duration INTEGER,
                      format TEXT CHECK(format in ('VIDEO','AUDIO')),
                      type TEXT CHECK(type IN ('STREAM', 'VIDEO')),
                      thumbnail_image_url TEXT,
                      video_id TEXT,
                      extracted_audio_filename TEXT
                      )'''

_channels_table = '''CREATE TABLE IF NOT EXISTS channels
                      (id SERIAL PRIMARY KEY,
                      channel TEXT,
                      scrap_streams BOOLEAN,
                      scrap_videos BOOLEAN)'''

_schedule_table = '''CREATE TABLE IF NOT EXISTS schedule
                      (id INTEGER PRIMARY KEY DEFAULT 1,
                      interval_minutes INTEGER NOT NULL DEFAULT 60,
                      enabled BOOLEAN NOT NULL DEFAULT TRUE)'''


def init_database():
    logging.info("Initialising Psql DB connection")
    conn = psycopg2.connect(**db_connection_params)
    if conn is not None:
        _create_table(conn, _rips_table)
        _create_table(conn, _channels_table)
        _create_table(conn, _schedule_table)
        _seed_schedule(conn)
    else:
        logging.error("Error! cannot create the database connection.")
    return conn


def _create_table(conn, create_table_sql):
    try:
        c = conn.cursor()
        table_name = create_table_sql.split()[5]
        c.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE lower(table_name) = %s)", (table_name,))
        result = c.fetchone()
        if not result[0]:
            c.execute(create_table_sql)
            logging.info(f'Table {table_name} created successfully')
        else:
            logging.info(f'Skipped Table create, table:{table_name} already exists')
        conn.commit()
    except psycopg2.Error as e:
        logging.error(f'Error occurred: {e}')


def get_all_channels(conn):
    try:
        cursor = conn.cursor()
        query = "SELECT channel, scrap_streams, scrap_videos FROM channels"
        cursor.execute(query)
        records = cursor.fetchall()
        channel_list = [
            {"channel": record[0], "scrap_streams": record[1], "scrap_videos": record[2]}
            for record in records
        ]
        cursor.close()
        return channel_list
    except psycopg2.Error as e:
        logging.error(f"Error fetching channels: {e}")
        return None


def check_video_id_exists(conn, video_id, format):
    try:
        cursor = conn.cursor()
        query = "SELECT EXISTS(SELECT 1 FROM rips WHERE video_id = %s AND format = %s LIMIT 1);"
        cursor.execute(query, (video_id, format))
        exists = cursor.fetchone()[0]
        cursor.close()
        return exists
    except psycopg2.Error as e:
        logging.error(f"Error checking video_id and format existence: {e}")
        return False


def insert_rip_record(conn, channel, video_title, duration, media_format, media_type,
                      thumbnail_image_url, video_id, extracted_audio_filename):
    try:
        with conn.cursor() as cur:
            insert_query = """
                INSERT INTO rips
                (channel, video_title, duration, format, type, thumbnail_image_url, video_id, extracted_audio_filename)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(insert_query, (
                channel,
                video_title,
                duration,
                media_format,
                media_type,
                thumbnail_image_url,
                video_id,
                extracted_audio_filename
            ))
            conn.commit()
            logging.info(f"✅ Rip record for video: {video_title} inserted successfully.")
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error inserting rip record: {e}")


def _seed_schedule(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO schedule (id, interval_minutes, enabled) VALUES (1, 60, TRUE) ON CONFLICT (id) DO NOTHING")
            conn.commit()
    except psycopg2.Error as e:
        logging.error(f"Error seeding schedule: {e}")


def get_schedule(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT interval_minutes, enabled FROM schedule WHERE id = 1")
            row = cur.fetchone()
            return {"interval_minutes": row[0], "enabled": row[1]}
    except psycopg2.Error as e:
        logging.error(f"Error fetching schedule: {e}")
        return {"interval_minutes": 60, "enabled": True}


def upsert_schedule(conn, interval_minutes, enabled):
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO schedule (id, interval_minutes, enabled) VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE SET interval_minutes = EXCLUDED.interval_minutes, enabled = EXCLUDED.enabled
            """, (interval_minutes, enabled))
            conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        logging.error(f"Error updating schedule: {e}")

import psycopg2
import utils
import hashlib
import logging

config = utils.load_config("config.json")
db_connection_params = {
    "dbname": config['DB_NAME'],
    "user": config['DB_USER'],
    "password": config['DB_PASS'],
    "host": config['DB_HOST'],
   # "port": config['DB_PORT']
}

posts_table = '''CREATE TABLE IF NOT EXISTS rips
                      (id SERIAL PRIMARY KEY,
                      creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      video_title TEXT,
                      duration INTEGER,
                      format TEXT CHECK(format in ('VIDEO','AUDIO')),
                      type TEXT CHECK(type IN ('STREAM', 'VIDEO')),
                      thumbnail_image_url TEXT,
                      video_id TEXT,
                      extracted_audio_filename TEXT 
                      )'''

users_table = '''CREATE TABLE IF NOT EXISTS channels
                      (id SERIAL PRIMARY KEY,
                      channel TEXT,
                      scrap_streams BOOLEAN,
                      scrap_videos BOOLEAN)'''



def init_database():
    logging.info("Initialising Psql DB connection")
    conn = psycopg2.connect(**db_connection_params)
    if conn is not None:
        _create_table(conn, posts_table)
        _create_table(conn, users_table)
    else:
        logging.error("Error! cannot create the database connection.")
    return conn


def _create_table(conn, create_table_sql):
    try:
        c = conn.cursor()
        table_name = create_table_sql.split()[5]
        c.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE lower(table_name) = %s)", (table_name,))
        result = c.fetchone()
        if not result[0]:  # Table does not exist
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
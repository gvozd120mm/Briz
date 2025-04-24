
import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")

def create_tables():
    commands = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            role VARCHAR(20) NOT NULL,
            username VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS apartments (
            id SERIAL PRIMARY KEY,
            owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            district VARCHAR(100),
            rooms INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            apartment_id INTEGER REFERENCES apartments(id) ON DELETE SET NULL,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ]

    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    for command in commands:
        cur.execute(command)
    conn.commit()
    cur.close()
    conn.close()

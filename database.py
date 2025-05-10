import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

load_dotenv()


def create_database():
    """Create the database if it doesn't exist"""
    try:
        # Connect to default postgres database to create our new database
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'simulation_games'")
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier("simulation_games"))
            )
            print("Database 'simulation_games' created successfully")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")
        raise


def get_connection():
    """Get a connection to the database"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database="simulation_games",
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise


def init_db():
    """Initialize the database with required tables"""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Create game1_terms table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS game1_terms (
                term VARCHAR(50) PRIMARY KEY,
                team1_value FLOAT,
                unit VARCHAR(20),
                team2_status VARCHAR(10) DEFAULT 'TBD',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert initial terms if empty
        cur.execute("SELECT COUNT(*) FROM game1_terms")
        if cur.fetchone()[0] == 0:
            initial_terms = [
                ("EBITDA", None, "$"),
                ("Interest Rate", None, "%"),
                ("Multiple", None, "x"),
                ("Factor Score", None, "x")
            ]
            cur.executemany(
                "INSERT INTO game1_terms (term, team1_value, unit) VALUES (%s, %s, %s)",
                initial_terms
            )

        conn.commit()
        cur.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    create_database()
    init_db()
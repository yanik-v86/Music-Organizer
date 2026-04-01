"""
Migration script to add log_metadata column to operation_logs table.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "music_organizer.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(operation_logs)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    if "log_metadata" not in existing_columns:
        print("Adding column: log_metadata")
        cursor.execute("ALTER TABLE operation_logs ADD COLUMN log_metadata TEXT DEFAULT ''")
    else:
        print("Column already exists: log_metadata")
    
    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()

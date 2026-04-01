"""
Migration script to add new columns to audio_files table.
Run this script to update the database schema.
"""
import sqlite3
from pathlib import Path

# Path to your database
DB_PATH = Path(__file__).parent / "music_organizer.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check which columns already exist
    cursor.execute("PRAGMA table_info(audio_files)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # New columns to add
    new_columns = [
        ("original_filepath", "TEXT DEFAULT ''"),
        ("file_size", "INTEGER DEFAULT 0"),
        ("bitrate", "TEXT DEFAULT ''"),
        ("sample_rate", "TEXT DEFAULT ''"),
        ("duration", "TEXT DEFAULT ''"),
    ]
    
    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            print(f"Adding column: {col_name}")
            cursor.execute(f"ALTER TABLE audio_files ADD COLUMN {col_name} {col_def}")
        else:
            print(f"Column already exists: {col_name}")
    
    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()

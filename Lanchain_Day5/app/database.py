from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "students.db"


STUDENTS = [
    ("22CS045", "Dhanushya", "Computer Science", 85, 72, 90, 78),
    ("22CS046", "Rahul", "Computer Science", 65, 70, 68, 72),
    ("22CS047", "Priya", "Information Technology", 92, 88, 95, 90),
    ("22CS048", "Arun", "Information Technology", 55, 60, 58, 62),
    ("22CS049", "Meena", "Computer Science", 78, 85, 80, 88),
]


def create_database(database_path: str | Path = DATABASE_PATH) -> Path:
    """Create or refresh the student database used by the tools."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                python INTEGER NOT NULL,
                database INTEGER NOT NULL,
                ai INTEGER NOT NULL,
                web INTEGER NOT NULL
            )
        """)
        cursor.execute("DELETE FROM students")

        cursor.executemany("""
            INSERT INTO students
            (student_id, name, department, python, database, ai, web)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, STUDENTS)
        connection.commit()
    finally:
        connection.close()
    return database_path


if __name__ == "__main__":
    create_database()
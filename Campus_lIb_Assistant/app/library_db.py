"""SQLite business database for event registration."""
import json
import time
from collections.abc import Callable
from pathlib import Path
from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "library.sql"


class LibraryDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn, self.clock = connect(path), clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM member").fetchone()[0]:
            return
        with self.transaction() as c:
            c.executemany("INSERT INTO member VALUES (?, ?, ?, ?, ?)", [
                (1, "DEMO001", "Asha Nair", "CSE", 3),
                (2, "DEMO002", "Ravi Shah", "ECE", 2),
                (3, "DEMO003", "Mina Joseph", "IT", 1),
                (4, "DEMO004", "Neha Verma", "CSE", 3),
                (5, "DEMO005", "Priyanka Iyer", "ECE", 3),
                (6, "DEMO006", "Sana Khan", "IT", 2),
                (7, "DEMO007", "Arjun Mehta", "ME", 3),
                (8, "DEMO008", "Karan Patel", "CE", 2)])
            c.executemany("INSERT INTO event VALUES (?, ?, ?, ?, ?, ?, ?, 0)", [
                (1, "AI in Education", "technology", "Main Auditorium", "2026-10-04 10:00", 2, 2),
                (2, "Cultural Fest", "cultural", "Open Grounds", "2026-10-05 17:00", 3, 1),
                (3, "Resume Workshop", "career", "Seminar Hall", "2026-10-06 14:00", 20, 20),
                (4, "Robotics Showcase", "technology", "Innovation Lab", "2026-10-07 11:00", 1, 0)])
            c.executemany("INSERT INTO policy VALUES (?, ?)", [("max_registrations", 3)])
            c.execute("INSERT INTO registration(member_id, event_id, created_at) VALUES (3, 2, ?)", (self.clock(),))
            c.execute("UPDATE event SET seats_available = seats_available - 1 WHERE id = 2")

    def get_member(self, roll_no: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM member WHERE roll_no = ?", (roll_no,)).fetchone()
        return dict(row) if row else None

    def policy(self, name: str) -> int:
        return self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()[0]

    def list_members(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT roll_no, name, dept FROM member ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def active_registrations(self, member_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT r.event_id, e.title FROM registration r JOIN event e ON e.id=r.event_id "
            "WHERE r.member_id=? ORDER BY r.id", (member_id,)).fetchall()
        return [dict(row) for row in rows]

    def search_events(self, text: str, limit: int = 5) -> list[dict]:
        like = f"%{text.strip()}%"
        rows = self.conn.execute(
            "SELECT id,title,category,venue,starts_at,seats_available FROM event "
            "WHERE title LIKE ? OR category LIKE ? OR venue LIKE ? ORDER BY starts_at LIMIT ?",
            (like, like, like, limit)).fetchall()
        return [dict(row) for row in rows]

    def get_event(self, event_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM event WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def register(self, member_id: int, event_id: int) -> str:
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM registration WHERE member_id=? AND event_id=?",
                         (member_id, event_id)).fetchone():
                return "already_registered"
            row = c.execute("SELECT version FROM event WHERE id=?", (event_id,)).fetchone()
            if row is None:
                return "unknown_event"
            changed = c.execute(
                "UPDATE event SET seats_available=seats_available-1, version=version+1 "
                "WHERE id=? AND seats_available>0 AND version=?", (event_id, row["version"])).rowcount
            if not changed:
                return "full"
            c.execute("INSERT INTO registration(member_id,event_id,created_at) VALUES (?,?,?)",
                      (member_id, event_id, self.clock()))
            return "registered"

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        cur = self.conn.execute(
            "INSERT INTO notification(roll_no,message,dedupe_key,created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(dedupe_key) DO NOTHING", (roll_no, message, dedupe_key, self.clock()))
        if cur.rowcount == 1:
            return cur.lastrowid, True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key=?", (dedupe_key,)).fetchone()[0], False

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        with self.transaction() as c:
            row = c.execute("SELECT result FROM idempotency WHERE key=?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            c.execute("INSERT INTO idempotency VALUES (?,?,?,?)",
                      (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True

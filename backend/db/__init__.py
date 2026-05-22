import json
import uuid
import aiosqlite

DB_PATH = "meetings.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                project_summary TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                name TEXT,
                transcript TEXT,
                summary TEXT,
                actions TEXT
            )
        """)
        # migrate: add project_summary column if it doesn't exist yet
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN project_summary TEXT")
        except Exception:
            pass
        await db.commit()


async def create_project(name: str) -> dict:
    pid = str(uuid.uuid4())[:8]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO projects (project_id, name) VALUES (?, ?)", (pid, name))
        await db.commit()
    return {"project_id": pid, "name": name}


async def list_projects() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT p.project_id, p.name, COUNT(m.id) AS meeting_count
            FROM projects p
            LEFT JOIN meetings m ON m.project_id = p.project_id
            GROUP BY p.project_id
        """) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_project(project_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT project_id, name FROM projects WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        project = dict(row)
        async with db.execute(
            "SELECT id, name, transcript, summary, actions FROM meetings WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ) as cursor:
            meetings = await cursor.fetchall()
    project["meetings"] = [
        {
            "id": m["id"],
            "name": m["name"],
            "transcript": m["transcript"],
            "summary": json.loads(m["summary"] or "{}"),
            "actions": json.loads(m["actions"] or "{}"),
        }
        for m in meetings
    ]
    return project


async def add_meeting(project_id: str, name: str, transcript: str, summary: dict, actions: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO meetings (project_id, name, transcript, summary, actions) VALUES (?, ?, ?, ?, ?)",
            (project_id, name, transcript, json.dumps(summary), json.dumps(actions)),
        )
        await db.commit()
        return cursor.lastrowid


async def meeting_count(project_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM meetings WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0


async def save_project_summary(project_id: str, summary: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET project_summary = ? WHERE project_id = ?",
            (json.dumps(summary), project_id),
        )
        await db.commit()


async def get_project_summary(project_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT project_summary FROM projects WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return json.loads(row[0])

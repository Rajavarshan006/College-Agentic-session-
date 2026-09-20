import os

from dotenv import load_dotenv

from app.library_db import LibraryDb
from app.memory import RunStore

load_dotenv()

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
LIBRARY_DB = os.environ.get("LIBRARY_DB", "library.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
PROVIDER = os.environ.get("PROVIDER", "gemini").lower()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")


def open_stores() -> tuple[RunStore, LibraryDb]:
    store, db = RunStore(AGENT_DB), LibraryDb(LIBRARY_DB)
    store.migrate()
    db.migrate()
    return store, db


def make_providers(mock: bool, slow: float = 0.0) -> dict:
    """Create the selected provider for the supervisor and both specialists."""
    if mock:
        from app.providers import demo_providers

        return demo_providers(slow)
    from app.providers import GeminiProvider, GroqProvider

    provider = (GroqProvider(GROQ_MODEL) if PROVIDER == "groq"
                else GeminiProvider(GEMINI_MODEL))
    return {"supervisor": provider, "catalogue": provider, "desk": provider}

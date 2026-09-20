import pytest
from app.agents import SupervisorTools, run_tool
from app.config import make_providers
from app.library_db import LibraryDb
from app.memory import RunStore
from app.worker import Worker
from app.tools.library_tools import DeskTools


@pytest.fixture
def db():
    value = LibraryDb(":memory:")
    value.migrate()
    return value


@pytest.fixture
def store():
    value = RunStore(":memory:")
    value.migrate()
    return value


def test_seed_has_events(db):
    assert db.count("event") == 4


def test_search_is_read_only(db):
    assert db.search_events("technology")[0]["title"] == "AI in Education"


def test_unknown_event(db):
    assert db.get_event(99) is None


def test_policy_is_data(db):
    assert db.policy("max_registrations") == 3


def test_registration_consumes_seat(db):
    assert db.register(1, 1) == "registered"
    assert db.get_event(1)["seats_available"] == 1


def test_registration_is_idempotent(db):
    assert db.register(1, 1) == "registered"
    assert db.register(1, 1) == "already_registered"


def test_full_event_refuses_registration(db):
    assert db.register(1, 4) == "full"


def test_limit_is_enforced_by_tool(db):
    desk = DeskTools(db, "DEMO002")
    assert desk.register_event(3)["status"] == "registered"
    assert desk.register_event(1)["status"] == "registered"
    assert desk.register_event(2)["error"] == "not_allowed"


def test_notification_is_deduplicated(db):
    desk = DeskTools(db, "DEMO001")
    assert desk.notify_member("Registered.")["duplicate"] is False
    assert desk.notify_member("Registered.")["duplicate"] is True


def test_supervisor_delegates_to_read_only_specialist(db):
    result, replayed = run_tool(SupervisorTools(db, make_providers(True), "DEMO001"), db, "k1",
                                "ask_catalogue", {"question": "Find AI in Education"})
    assert result["agent"] == "catalogue" and not replayed


def test_end_to_end_registration(store, db):
    thread = store.create_thread("DEMO001")
    run_id = store.enqueue(thread, "AI in Education", "mock")
    Worker(store, db, make_providers(True), worker_id="test").run_until_idle()
    assert store.get_run(run_id)["status"] == "succeeded"
    assert db.count("registration") == 2


def test_crash_replay_is_safe(store, db):
    thread = store.create_thread("DEMO001")
    run_id = store.enqueue(thread, "AI in Education", "mock")
    original = db.once

    def crash(key, tool, effect):
        result = original(key, tool, effect)
        if tool == "register_event":
            raise BaseException("simulated crash")
        return result

    db.once = crash
    with pytest.raises(BaseException):
        Worker(store, db, make_providers(True), worker_id="dead", lease_seconds=1).run_once()
    db.once = original
    store.clock = lambda: 9999999999.0
    Worker(store, db, make_providers(True), worker_id="replay").run_until_idle()
    assert store.get_run(run_id)["status"] == "succeeded"
    assert db.count("registration") == 2

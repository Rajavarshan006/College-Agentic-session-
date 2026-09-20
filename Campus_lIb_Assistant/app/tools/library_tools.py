"""Least-privilege event tools. Docstrings are part of the agent prompt."""
from datetime import datetime, timezone
from app.idempotency import notification_dedupe_key
from app.library_db import LibraryDb
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()
    DELEGATES: tuple[str, ...] = ()
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {name: getattr(self, name) for name in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class CatalogueTools(Toolset):
    """Read-only event discovery specialist."""
    TOOL_NAMES = ("search_events", "get_event")

    def __init__(self, db: LibraryDb):
        self.db = db

    def search_events(self, text: str) -> dict:
        """Find events by title, category, or venue.

        Use for discovery and availability questions. Do not use for registration or notifications;
        this tool is read-only and changes nothing.
        """
        if not text.strip():
            return {"error": "empty_query", "hint": "Pass event title, category, or venue."}
        return {"events": self.db.search_events(text)}

    def get_event(self, event_id: int) -> dict:
        """Get one event's schedule and seats.

        Use after search_events when an event id is known. Do not use to register a member;
        this tool is read-only and changes nothing.
        """
        event = self.db.get_event(event_id)
        return {"error": "unknown_event"} if event is None else {"event": event}


class DeskTools(Toolset):
    """Registration desk bound to one member."""
    TOOL_NAMES = ("get_member", "check_can_register", "register_event", "notify_member")
    SIDE_EFFECTS = ("register_event", "notify_member")

    def __init__(self, db: LibraryDb, roll_no: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.roll_no, self.clock = db, roll_no, clock

    def _member(self) -> dict:
        member = self.db.get_member(self.roll_no)
        if member is None:
            raise LookupError(f"member {self.roll_no} not found")
        return member

    def get_member(self) -> dict:
        """Show this member's registrations.

        Use for this member's account and registration questions. Do not use to change a
        registration; this tool is read-only and changes nothing.
        """
        member = self._member()
        return {**member, "registrations": self.db.active_registrations(member["id"])}

    def check_can_register(self) -> dict:
        """Check the policy-table registration limit before registering.

        Use before register_event or when explaining eligibility. Do not treat it as a
        registration action; this tool is read-only and changes nothing.
        """
        member = self._member()
        current = len(self.db.active_registrations(member["id"]))
        limit = self.db.policy("max_registrations")
        reasons = [] if current < min(member["max_registrations"], limit) else [
            f"already has {current} registrations; limit is {min(member['max_registrations'], limit)}"]
        return {"can_register": not reasons, "reasons": reasons}

    def register_event(self, event_id: int) -> dict:
        """Register this member for an event.

        Use only after the member explicitly confirmed the booking and check_can_register allows
        it. Do not use for availability-only questions or without confirmation. CHANGES DATA:
        consumes one seat and creates a registration; repeating the same request is safe.
        """
        verdict = self.check_can_register()
        if not verdict["can_register"]:
            return {"error": "not_allowed", "reasons": verdict["reasons"]}
        event = self.db.get_event(event_id)
        if event is None:
            return {"error": "unknown_event"}
        status = self.db.register(self._member()["id"], event_id)
        return {"error": "event_full"} if status == "full" else {
            "event_id": event_id, "title": event["title"], "status": status}

    def notify_member(self, message: str) -> dict:
        """Send a confirmation message, once per day and exact text.

        Use only after a successful registration or another completed desk action. Do not use
        to answer ordinary questions or before the member confirms a booking. CHANGES DATA:
        creates one deduplicated notification record.
        """
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message"}
        key = notification_dedupe_key(self.roll_no, message, self.clock().date())
        notification_id, created = self.db.record_notification(self.roll_no, message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}

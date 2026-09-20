"""Supervisor plus read-only discovery and side-effect registration specialists."""
import time
from collections.abc import Callable
from app.idempotency import idempotency_key
from app.library_db import LibraryDb
from app.providers import AgentError
from app.tools.library_tools import CatalogueTools, DeskTools, Toolset

SPECIALIST_MAX_STEPS = 6
SUPERVISOR_SYSTEM = """You are the Campus Events Assistant for member {roll_no}.
Delegate event discovery to ask_catalogue and registrations/messages to ask_desk.
Never invent event ids or policy decisions. Give each specialist a complete request and answer briefly."""
CATALOGUE_SYSTEM = "You are a read-only event catalogue specialist. Find events and report ids, schedules, and seats."
DESK_SYSTEM = """You are the registration desk for member {roll_no}. Always call check_can_register before
register_event. Use the policy result, register only when requested, and notify after success."""


def run_tool(toolset: Toolset, db: LibraryDb, key: str, name: str, args: dict) -> tuple[dict, bool]:
    try:
        if name in toolset.DELEGATES:
            return toolset.delegate(name, args, key), False
        if name in toolset.SIDE_EFFECTS:
            result, fresh = db.once(key, name, lambda: toolset.call(name, args))
            return result, not fresh
        return toolset.call(name, args), False
    except AgentError:
        raise
    except Exception as exc:
        return {"error": "tool_failed", "hint": f"{name} failed ({type(exc).__name__})"}, False


def run_specialist(agent: str, system: str, toolset: Toolset, *, db: LibraryDb, provider,
                   task: str, parent_key: str, on_step: Callable[[dict], None] | None = None) -> dict:
    contents, used, seq = [{"role": "user", "text": task}], [], 0
    while seq < SPECIALIST_MAX_STEPS:
        turn = provider.generate(system, contents, list(toolset.functions().values()))
        seq += 1
        if not turn.tool_calls:
            return {"agent": agent, "answer": turn.text or "", "tools_used": used}
        contents.append({"role": "model", "text": turn.text, "raw": turn.raw,
                         "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]})
        for call in turn.tool_calls:
            seq += 1
            result, replayed = run_tool(toolset, db, idempotency_key(parent_key, seq, call.name, call.args),
                                        call.name, call.args)
            used.append(call.name)
            if on_step:
                on_step({"agent": agent, "kind": "tool", "tool": call.name, "args": call.args,
                         "result": result, "ok": "error" not in result, "replayed": replayed})
            contents.append({"role": "tool", "name": call.name, "result": result})
    return {"agent": agent, "error": "specialist_step_limit", "tools_used": used}


class SupervisorTools(Toolset):
    TOOL_NAMES = ("ask_catalogue", "ask_desk")
    DELEGATES = TOOL_NAMES

    def __init__(self, db: LibraryDb, providers: dict, roll_no: str, on_step=None):
        self.db, self.providers, self.roll_no, self.on_step = db, providers, roll_no, on_step

    def ask_catalogue(self, question: str) -> dict:
        """Ask the read-only catalogue specialist. Use for event search and availability."""
        raise RuntimeError("delegations run through delegate()")

    def ask_desk(self, request: str) -> dict:
        """Ask the desk specialist. Use for registrations, account details, and confirmations."""
        raise RuntimeError("delegations run through delegate()")

    def delegate(self, name: str, args: dict, key: str) -> dict:
        field = "question" if name == "ask_catalogue" else "request"
        if set(args) != {field} or not isinstance(args[field], str) or not args[field].strip():
            return {"error": "invalid_arguments", "hint": f"{name} takes one non-empty string"}
        if self.on_step:
            self.on_step({"agent": "supervisor", "kind": "delegate", "tool": name, "args": args})
        if name == "ask_catalogue":
            return run_specialist("catalogue", CATALOGUE_SYSTEM, CatalogueTools(self.db), db=self.db,
                                  provider=self.providers["catalogue"], task=args[field],
                                  parent_key=key, on_step=self.on_step)
        return run_specialist("desk", DESK_SYSTEM.format(roll_no=self.roll_no), DeskTools(self.db, self.roll_no),
                              db=self.db, provider=self.providers["desk"], task=args[field],
                              parent_key=key, on_step=self.on_step)

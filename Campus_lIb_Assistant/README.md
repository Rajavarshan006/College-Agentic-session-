# Campus Event Registration Assistant

An end-to-end agent service that helps students discover campus events and register for them
without consuming a seat or sending a notification until the student explicitly confirms.

## 1. Architecture

```text
Student
  |
  v
Streamlit UI (app.py) or CLI (scripts/)
  |
  | create thread + enqueue question
  v
agent.db queue (RunStore)
  |
  v
Worker (lease, heartbeat, retry, replay)
  |
  v
Supervisor agent
  |------------------------------|
  v                              v
Catalogue specialist             Registration desk specialist
read-only tools                  member, policy, registration, notification tools
  |                              |
  |                              v
  |                         library.db
  v
library.db
events, members, policies, registrations, notifications, idempotency keys
```

### Component responsibilities

| Component | File(s) | Responsibility | Writes data? |
|---|---|---|---|
| Streamlit interface | `app.py` | Collects the student, displays responses, and presents booking approval buttons | Only through the worker flow |
| CLI entry points | `scripts/demo.py`, `scripts/ask.py`, `scripts/worker.py` | Run scripted demonstrations, queue questions, and run a worker | Through the worker flow |
| Queue and memory | `app/memory.py`, `schema/agent.sql` | Stores threads, messages, jobs, leases, attempts, model steps, and tool results | Yes, `agent.db` |
| Worker | `app/worker.py`, `app/runner.py` | Claims jobs, renews leases, executes agents, retries failures, and resumes after crashes | Yes, both databases through tools |
| Supervisor | `app/agents.py` | Routes the question to the correct specialist and produces the final answer | No direct business-data writes |
| Catalogue specialist | `app/agents.py`, `app/tools/library_tools.py` | Searches events and reads event details | No |
| Registration desk specialist | `app/agents.py`, `app/tools/library_tools.py` | Checks policy, registers a member, and records a notification | Yes |
| Business database | `app/library_db.py`, `schema/library.sql` | Enforces event capacity, registration uniqueness, policy limits, and safe writes | Yes, `library.db` |
| Model providers | `app/providers.py`, `app/config.py` | Supports Groq, Gemini, and deterministic scripted models | No |

## 2. Request flows

### Event discovery

| Step | Actor | Action | Result | Side effect |
|---:|---|---|---|---|
| 1 | Student | Enters an event question | Streamlit creates a thread and queue job | User message stored in `agent.db` |
| 2 | Worker | Claims the job with a lease | Job becomes `running` | Lease and attempt recorded |
| 3 | Supervisor | Interprets the request | Delegates to `ask_catalogue` | Delegation step recorded |
| 4 | Catalogue specialist | Calls `search_events` or `get_event` | Returns title, category, venue, schedule, and current seats | No business data changes |
| 5 | Supervisor | Summarizes the specialist result | Answer is shown to the student | Final response stored in `agent.db` |

### Booking approval

Booking requests intentionally use two phases:

| Phase | Actor | Action | Allowed tools | Database effect |
|---|---|---|---|---|
| Availability check | Catalogue specialist | Finds the requested event and reports available seats | `search_events`, `get_event` | Read-only |
| Student decision | Streamlit UI | Shows `Confirm Booking` and `Decline Booking` | UI controls only | No change |
| Confirmation | Registration desk specialist | Checks policy, registers the member, and sends confirmation | `get_member`, `check_can_register`, `register_event`, `notify_member` | Consumes one seat and records one notification |
| Decline | Streamlit UI | Clears the pending approval | No tools | No registration or notification |

The first availability phase cannot call write tools. The registration side effect is only reachable
from the second worker run after the student clicks `Confirm Booking`.

### Crash and replay

| Step | Event | Durable behavior |
|---:|---|---|
| 1 | Worker claims a job | Lease owner and expiry are stored |
| 2 | Worker performs a side effect | Registration and idempotency key commit together |
| 3 | Worker dies before recording the tool step | Lease eventually expires |
| 4 | Another worker reclaims the job | Recorded model steps are rebuilt |
| 5 | Same side effect is requested again | Stored idempotency result is replayed; no duplicate seat or message |

## 3. Agent tools and permissions

Every tool description states when it should be used and whether it changes data.

| Specialist | Tool | Type | Purpose | Business effect |
|---|---|---|---|---|
| Catalogue | `search_events(text)` | Read-only | Search by event title, category, or venue | None |
| Catalogue | `get_event(event_id)` | Read-only | Read one event's details | None |
| Desk | `get_member()` | Read-only | Read the bound student's registrations | None |
| Desk | `check_can_register()` | Read-only | Enforce the registration policy from the database | None |
| Desk | `register_event(event_id)` | Side effect | Reserve one seat for the bound student | Decrements available seats |
| Desk | `notify_member(message)` | Side effect | Record a confirmation notification | Creates one notification record |
| Supervisor | `ask_catalogue(question)` | Delegation | Ask the read-only specialist | Depends on specialist |
| Supervisor | `ask_desk(request)` | Delegation | Ask the desk specialist | May change business data |

The desk specialist is bound to the selected roll number. The model cannot substitute another
student identity in a tool call.

## 4. Database design

### `library.db` — business data

| Table | Important columns | Purpose | Integrity rule |
|---|---|---|---|
| `member` | `roll_no`, `name`, `max_registrations` | Seeded student identities | Unique roll number |
| `event` | `title`, `category`, `venue`, `starts_at`, `seats_available`, `version` | Event catalogue and capacity | Available seats cannot be negative |
| `policy` | `name`, `value` | Business rules stored as data | Registration limit is read by tools |
| `registration` | `member_id`, `event_id`, `created_at` | Successful registrations | Unique member/event pair |
| `notification` | `roll_no`, `message`, `dedupe_key` | Confirmation messages | Unique deduplication key |
| `idempotency` | `key`, `tool_name`, `result` | Side-effect replay records | Unique effect key |

### `agent.db` — agent memory and queue

| Table | Purpose |
|---|---|
| `thread` | Conversation identity and selected student |
| `message` | Append-only user and assistant messages |
| `run` | Queue status, attempts, lease owner, cancellation, and errors |
| `run_step` | Durable model and tool execution steps |
| `tool_call` | Tool arguments, result, latency, success, and idempotency key |

Business data never lives in `agent.db`, and agent memory never lives in `library.db`.

## 5. Safety and reliability

- **Capacity safety:** registration uses a transaction and optimistic `version` checking.
- **Duplicate safety:** `(member_id, event_id)` prevents duplicate registrations.
- **Idempotency:** side effects use `LibraryDb.once()` and persist their result.
- **Policy enforcement:** `check_can_register()` reads the database policy; the tool enforces it
  again inside `register_event()`.
- **Least privilege:** the catalogue specialist has no write tools.
- **Lease recovery:** expired jobs are requeued and can be picked up by another worker.
- **Provider errors:** rate limits, unavailable providers, missing dependencies, and unavailable
  models are surfaced as explicit run error codes.

## 6. Provider configuration

Edit the local [.env](./.env) file:

```env
PROVIDER=groq
GROQ_API_KEY=your_real_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.6-flash

USE_MOCK_MODE=false
```

Use `PROVIDER=groq` or `PROVIDER=gemini`. The selected provider is shared by the supervisor and
both specialists. Use `USE_MOCK_MODE=true` for deterministic local UI testing without an API key.
The `.env` file is excluded by [.gitignore](./.gitignore); use [.env.example](./.env.example) as
the safe template.

## 7. Project structure

| Path | Contents |
|---|---|
| `app.py` | Streamlit application and approval UI |
| `app/agents.py` | Supervisor, specialist loops, delegation, and idempotency keys |
| `app/library_db.py` | Event database queries and safe writes |
| `app/memory.py` | Queue, leases, retries, history, and durable steps |
| `app/providers.py` | Gemini, Groq, and scripted provider adapters |
| `app/runner.py` | Resumable execution of a claimed run |
| `app/worker.py` | Worker lifecycle and error handling |
| `app/tools/library_tools.py` | Least-privilege domain tools |
| `schema/library.sql` | Business database schema |
| `schema/agent.sql` | Agent memory and queue schema |
| `scripts/demo.py` | No-key end-to-end and crash demonstrations |
| `tests/test_event_service.py` | Automated behavior and replay tests |

## 8. Installation and commands

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# No API key required
python -m scripts.demo
python -m scripts.demo --crash
pytest

# Interactive UI
streamlit run app.py
```

The seeded identities are:

| Roll No | Name | Department |
|---|---|---|
| DEMO001 | Asha Nair | CSE |
| DEMO002 | Ravi Shah | ECE |
| DEMO003 | Mina Joseph | IT |
| DEMO004 | Neha Verma | CSE |
| DEMO005 | Priyanka Iyer | ECE |
| DEMO006 | Sana Khan | IT |
| DEMO007 | Arjun Mehta | ME |
| DEMO008 | Karan Patel | CE |

The higher-grade retry feature is included: retryable worker failures use exponential backoff
and runs become `dead` after the configured maximum attempts. A threaded race test and second
terminal cancellation flow were not included.

## 9. Validation coverage

| Check | Command | Expected result |
|---|---|---|
| Unit and integration tests | `pytest` | 12 tests pass |
| Scripted end-to-end flow | `python -m scripts.demo` | Discovery, approval-style scripted registration, and refusal complete |
| Crash replay | `python -m scripts.demo --crash` | `PASS` with one registration and one notification |
| Streamlit UI | `streamlit run app.py` | UI starts and displays provider, events, response, and approval controls |

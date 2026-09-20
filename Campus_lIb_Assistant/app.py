import os
import uuid
import streamlit as st

from app.agents import CATALOGUE_SYSTEM, run_specialist
from app.config import GROQ_MODEL, GEMINI_MODEL, PROVIDER, make_providers, open_stores
from app.providers import AgentError
from app.tools.library_tools import CatalogueTools
from app.worker import Worker

st.set_page_config(page_title="Campus Events Assistant", page_icon="🎟️")
st.title("Campus Events Assistant")
st.caption("Search events, register safely, and receive one confirmation message.")

store, db = open_stores()
mock_mode = os.environ.get("USE_MOCK_MODE", "").lower() in {"1", "true", "yes"}
active_provider = "scripted mock" if mock_mode else (f"{PROVIDER}/{GROQ_MODEL}" if PROVIDER == "groq" else f"{PROVIDER}/{GEMINI_MODEL}")
st.caption(f"Provider: {active_provider}")
members = db.list_members()
member_roll_numbers = [member["roll_no"] for member in members]
member_labels = {member["roll_no"]: f"{member['roll_no']} - {member['name']} ({member['dept']})" for member in members}
roll_no = st.selectbox("Student", member_roll_numbers, format_func=lambda value: member_labels[value])
question = st.text_input("What would you like to do?", placeholder="Is AI in Education available? Register me if there is space.")

def is_booking_request(text: str) -> bool:
    words = text.lower().split()
    return any(word in words for word in (
        "book", "booking", "register", "registration", "reserve", "reservation",
        "seat", "seats", "available", "availability",
    ))


def run_assistant_request(text: str) -> tuple[str, str]:
    providers = make_providers(mock=mock_mode)
    thread = store.create_thread(roll_no)
    run_id = store.enqueue(thread, text, providers["supervisor"].model)
    with st.spinner("The assistant is working..."):
        Worker(store, db, providers, worker_id="streamlit-worker").run_until_idle()
    run = store.get_run(run_id)
    if run["status"] != "succeeded":
        return "", run["error_code"] or "unknown error"
    return store.load_history(thread)[-1]["text"], ""


def run_availability_check(text: str) -> tuple[str, str]:
    providers = make_providers(mock=mock_mode)
    try:
        result = run_specialist(
            "catalogue",
            CATALOGUE_SYSTEM,
            CatalogueTools(db),
            db=db,
            provider=providers["catalogue"],
            task=f"Check this event request and report the current available seat count. Do not register anyone: {text}",
            parent_key=f"streamlit-availability-{uuid.uuid4()}",
        )
    except AgentError as exc:
        return "", exc.code
    return result.get("answer", ""), result.get("error", "")


if st.button("Ask assistant", type="primary", disabled=not question.strip()):
    booking_request = is_booking_request(question)
    if booking_request:
        response, error = run_availability_check(question)
    else:
        response, error = run_assistant_request(question)
    if not error:
        st.session_state["assistant_response"] = response
        st.session_state["pending_booking"] = booking_request
        st.session_state["booking_question"] = question
    else:
        st.error(f"Run ended with an error: {error}")
        if error == "provider_rate_limited":
            st.info("The provider's current quota or rate limit was reached. Wait and retry, or check your provider limits.")
        elif error == "provider_model_not_found":
            st.info("The configured model is unavailable for this Groq key. Update GROQ_MODEL in .env.")
        else:
            st.caption("Check the configured provider API key and terminal output for details.")

if st.session_state.get("assistant_response"):
    st.success(st.session_state["assistant_response"])

if st.session_state.get("pending_booking"):
    st.info("Review the available-seat information before confirming your booking.")
    confirm, decline = st.columns(2)
    with confirm:
        if st.button("Confirm Booking", type="primary"):
            response, error = run_assistant_request(
                st.session_state["booking_question"]
                + "\n\nThe member has confirmed the booking. Complete the registration and send the confirmation notification."
            )
            if error:
                st.error(f"Booking could not be completed: {error}")
            else:
                st.success(response)
                st.session_state["pending_booking"] = False
    with decline:
        if st.button("Decline Booking"):
            st.session_state["pending_booking"] = False
            st.info("Booking declined. No registration was made.")

st.subheader("Upcoming events")
for event in db.search_events(""):
    st.write(f"**{event['title']}** · {event['category']} · {event['venue']}")

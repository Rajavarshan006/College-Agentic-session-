import streamlit as st

from app.agent import ask_student_agent
from app.database import create_database


def run_app() -> None:
    st.set_page_config(page_title="Student Information Agent", page_icon="🎓")
    create_database()
    st.title("🎓 Student Information Agent")
    st.caption("Ask about student details, marks, totals, averages, or passing eligibility.")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Type your Question...")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                answer = ask_student_agent(question)
            except (RuntimeError, ValueError) as error:
                answer = str(error)
                st.error(answer)
            else:
                st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})

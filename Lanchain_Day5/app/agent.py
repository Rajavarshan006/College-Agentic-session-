import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.agents import create_agent

from app.tools import (
    get_student_info,
    get_student_marks,
    calculator,
    get_passing_rules
)


TOOLS = [
    get_student_info,
    get_student_marks,
    calculator,
    get_passing_rules
]


SYSTEM_PROMPT = """
You are a student information assistant.

Use the available tools to answer student-related questions accurately.

Use tools for every student fact and calculation.
For totals and averages, use the calculator tool rather than mental math.
For eligibility, verify both the overall average and every subject mark against
the passing rules.
Do not invent student data or rules.
"""


def create_student_agent():

    load_dotenv()

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to .env before using the agent."
        )

    model = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0
    )

    return create_agent(model, TOOLS, system_prompt=SYSTEM_PROMPT)


def ask_student_agent(question: str) -> str:

    if not question.strip():
        raise ValueError("Question cannot be empty.")

    result = create_student_agent().invoke({
        "messages": [{"role": "user", "content": question}]
    })

    return result["messages"][-1].content
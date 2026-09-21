# Student Information Agent

A Streamlit application that answers questions about student details, marks, totals,
averages, and passing eligibility through a LangChain tool-calling agent powered by
Google Gemini.

## Features

- SQLite database seeded with the five students from the assignment.
- LangChain tools for student information, marks, safe arithmetic, and passing rules.
- Gemini chooses which tools to call instead of using a fixed sequence.
- Chat-style Streamlit interface with conversation history.
- Unit tests for database seeding, tools, validation, and agent input handling.

## Requirements

- Python 3.10+
- A Google Gemini API key

The existing `requirements.txt` contains the Python dependencies. If Streamlit is
not already present in that file, install it separately:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt streamlit
```

## Configuration

Create a `.env` file in the project root:

```text
GOOGLE_API_KEY=your-gemini-api-key
```

Do not commit `.env` or expose the API key. The included `.gitignore` excludes it.

## Run the application

From the project root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The database is created and seeded automatically when the app starts.

Example questions:

- `What is the name and department of student 22CS045?`
- `What are the marks of 22CS047?`
- `What is the total and average mark of 22CS045?`
- `Is 22CS045 eligible to pass according to the university rules?`
- `I am 22CS045. Tell me my name, department, total marks, average marks, and whether I satisfy the university passing requirements.`

## Run tests

The tests do not call Gemini and can run without an API key:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Project structure

```text
app.py              Streamlit entrypoint
app/database.py     SQLite setup and seed data
app/tools.py        LangChain tools
app/agent.py        Lazy Gemini agent construction and invocation
app/main.py         Streamlit UI
tests/              Unit tests
students.db         Local SQLite database
```

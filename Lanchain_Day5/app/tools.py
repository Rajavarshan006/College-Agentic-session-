import ast
import operator
import sqlite3
from langchain.tools import tool

from app.database import DATABASE_PATH


_OPERATORS = {
    ast.Add: operator.add,
    ast.Div: operator.truediv,
    ast.Mult: operator.mul,
    ast.Pow: operator.pow,
    ast.Sub: operator.sub,
    ast.USub: operator.neg,
}


def _evaluate_expression(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate_expression(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](
            _evaluate_expression(node.left),
            _evaluate_expression(node.right),
        )
    raise ValueError


@tool
def get_student_info(student_id: str) -> str:
    """Get the name and department of a student."""

    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT name, department FROM students WHERE student_id = ?",
        (student_id,)
    )

    student = cursor.fetchone()
    connection.close()

    if student is None:
        return f"No student found with ID {student_id}."

    return f"Name: {student[0]}, Department: {student[1]}"


@tool
def get_student_marks(student_id: str) -> str:
    """Get the marks of a student in Python, Database, AI, and Web."""

    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT python, database, ai, web
        FROM students
        WHERE student_id = ?
        """,
        (student_id,)
    )

    marks = cursor.fetchone()
    connection.close()

    if marks is None:
        return f"No student found with ID {student_id}."

    return (
        f"Python: {marks[0]}, "
        f"Database: {marks[1]}, "
        f"AI: {marks[2]}, "
        f"Web: {marks[3]}"
    )


@tool
def calculator(expression: str) -> str:
    """Calculate a mathematical expression."""

    try:
        return str(_evaluate_expression(ast.parse(expression, mode="eval").body))
    except Exception:
        return "Invalid mathematical expression."


@tool
def get_passing_rules() -> str:
    """Get the university passing rules."""

    return (
        "Minimum overall average: 40%. "
        "Minimum mark in each subject: 35%."
    )
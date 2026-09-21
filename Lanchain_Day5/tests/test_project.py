import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import tools
from app.database import create_database


class StudentProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "students.db"
        create_database(database_path)
        self.database_patch = patch.object(tools, "DATABASE_PATH", database_path)
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_database_contains_all_sample_students(self):
        with tools.DATABASE_PATH.open("rb") as database_file:
            self.assertGreater(len(database_file.read()), 0)
        self.assertIn("Dhanushya", tools.get_student_info.invoke({"student_id": "22CS045"}))

    def test_student_info_and_marks(self):
        self.assertEqual(
            tools.get_student_info.invoke({"student_id": "22CS045"}),
            "Name: Dhanushya, Department: Computer Science",
        )
        self.assertEqual(
            tools.get_student_marks.invoke({"student_id": "22CS045"}),
            "Python: 85, Database: 72, AI: 90, Web: 78",
        )

    def test_unknown_student_is_reported(self):
        self.assertEqual(
            tools.get_student_info.invoke({"student_id": "unknown"}),
            "No student found with ID unknown.",
        )

    def test_calculator_handles_totals_averages_and_rejects_code(self):
        self.assertEqual(tools.calculator.invoke({"expression": "85 + 72 + 90 + 78"}), "325")
        self.assertEqual(tools.calculator.invoke({"expression": "(325) / 4"}), "81.25")
        self.assertEqual(
            tools.calculator.invoke({"expression": "__import__('os').getcwd()"}),
            "Invalid mathematical expression.",
        )

    def test_passing_rules_are_available(self):
        rules = tools.get_passing_rules.invoke({})
        self.assertIn("40%", rules)
        self.assertIn("35%", rules)

    def test_agent_rejects_empty_questions_before_model_call(self):
        from app.agent import ask_student_agent

        with self.assertRaises(ValueError):
            ask_student_agent("   ")


if __name__ == "__main__":
    unittest.main()

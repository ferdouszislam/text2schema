import sqlite3
import unittest
from contextlib import closing

from create_query_generator.create_query_generator import generate_create_queries
from verifier.verify import verify_schema


class GenerateCreateQueriesTests(unittest.TestCase):
    def test_verified_student_schema_generates_executable_tables(self):
        schema = """
        Student(<u>Student_Id</u>, Student_Name, Student_DOB)
        Course(<u>Course_Id</u>, Course_Title, Course_Description)
        CoursesTaken(<u>Student_Id</u>, <u>Course_Id</u>, Course_Grade)
        """
        dependencies = [
            "[Student_Id] -> [Student_Name, Student_DOB]",
            "[Course_Id] -> [Course_Title, Course_Description]",
            "[Student_Id, Course_Id] -> [Course_Grade]",
        ]
        types = {
            "Student_Id": "INTEGER",
            "Course_Id": "INTEGER",
            "Student_Name": "VARCHAR(100)",
            "Student_DOB": "DATE",
            "Course_Title": "TEXT",
            "Course_Description": "TEXT",
            "Course_Grade": "REAL",
        }

        result = verify_schema(schema, dependencies)
        self.assertTrue(result["verified"], result["feedback"])
        queries = generate_create_queries(schema, types)
        self.assertEqual(len(queries), 3)
        self.assertTrue(all(query.endswith(";") for query in queries))
        with closing(sqlite3.connect(":memory:")) as connection:
            for query in queries:
                connection.execute(query)
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid"
            ).fetchall()
            self.assertEqual(tables, [("Student",), ("Course",), ("CoursesTaken",)])
            columns = connection.execute('PRAGMA table_info("CoursesTaken")').fetchall()
            self.assertEqual(
                [(column[1], column[2], column[3], column[5]) for column in columns],
                [
                    ("Student_Id", "INTEGER", 1, 1),
                    ("Course_Id", "INTEGER", 1, 2),
                    ("Course_Grade", "REAL", 0, 0),
                ],
            )
            foreign_keys = connection.execute('PRAGMA foreign_key_list("CoursesTaken")').fetchall()
            self.assertEqual(foreign_keys, [])
            connection.execute('INSERT INTO "Student" VALUES (1, ?, NULL)', ("Sam",))
            connection.execute('INSERT INTO "Course" VALUES (10, ?, NULL)', ("Databases",))
            connection.execute('INSERT INTO "CoursesTaken" VALUES (1, 10, 90.5)')
            connection.execute('INSERT INTO "CoursesTaken" VALUES (1, 11, 92.5)')
            enrollment = connection.execute(
                'SELECT Student_Name, Course_Title, Course_Grade '
                'FROM "CoursesTaken" NATURAL JOIN "Student" NATURAL JOIN "Course"'
            ).fetchall()
            self.assertEqual(enrollment, [("Sam", "Databases", 90.5)])
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('INSERT INTO "CoursesTaken" VALUES (1, 10, 80.0)')
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('INSERT INTO "CoursesTaken" VALUES (NULL, 12, 88.0)')

    def test_quotes_reserved_names_and_preserves_qualified_name(self):
        queries = generate_create_queries(
            "Order(<u>From</u>, Order.Select)",
            {"From": "INTEGER", "Order.Select": "VARCHAR(60)"},
        )
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute(queries[0])
            connection.execute(
                'INSERT INTO "Order" ("From", "Order.Select") VALUES (?, ?)', (1, "sample")
            )
            self.assertEqual(
                connection.execute('SELECT "Order.Select" FROM "Order" WHERE "From" = 1').fetchall(),
                [("sample",)],
            )

    def test_shared_non_key_attribute_uses_one_type(self):
        queries = generate_create_queries(
            "Parent(<u>Parent_Id</u>, Shared_Label)\nChild(<u>Child_Id</u>, Shared_Label)",
            {"Parent_Id": "INTEGER", "Child_Id": "INTEGER", "Shared_Label": " varchar ( 60 ) "},
        )
        with closing(sqlite3.connect(":memory:")) as connection:
            for query in queries:
                connection.execute(query)
            for table in ("Parent", "Child"):
                with self.subTest(table=table):
                    column = connection.execute(f'PRAGMA table_info("{table}")').fetchall()[1]
                    self.assertEqual((column[1], column[2], column[5]), ("Shared_Label", "VARCHAR(60)", 0))

    def test_rejects_attribute_repeated_within_one_relation(self):
        with self.assertRaisesRegex(ValueError, "Student_Id"):
            generate_create_queries(
                "Student(<u>Student_Id</u>, Student_Id)",
                {"Student_Id": "INTEGER"},
            )

    def test_distinct_attributes_with_same_suffix_keep_distinct_types(self):
        queries = generate_create_queries(
            "Student(Student_Name)\nCourse(Course_Name)",
            {"Student_Name": "TEXT", "Course_Name": "VARCHAR(100)"},
        )
        with closing(sqlite3.connect(":memory:")) as connection:
            for query in queries:
                connection.execute(query)
            self.assertEqual(connection.execute('PRAGMA table_info("Student")').fetchone()[2], "TEXT")
            self.assertEqual(connection.execute('PRAGMA table_info("Course")').fetchone()[2], "VARCHAR(100)")

    def test_rejects_missing_and_unknown_type_keys(self):
        cases = [
            ({"Id": "INTEGER"}, "Value"),
            ({"Id": "INTEGER", "Value": "TEXT", "Extra": "TEXT"}, "Extra"),
        ]
        for types, bad_name in cases:
            with self.subTest(types=types), self.assertRaisesRegex(ValueError, bad_name):
                generate_create_queries("R(<u>Id</u>, Value)", types)

    def test_rejects_constraints_and_statement_syntax_as_types(self):
        for type_sql in ("TEXT NOT NULL", "INTEGER PRIMARY KEY", "TEXT; INT", "TEXT, INT"):
            with self.subTest(type_sql=type_sql), self.assertRaises(ValueError):
                generate_create_queries("R(Value)", {"Value": type_sql})

    def test_rejects_sqlite_name_collisions_and_reserved_table_prefix(self):
        cases = [
            ("Records(A)\nrecords(B)", {"A": "TEXT", "B": "TEXT"}),
            ("Records(Label, label)", {"Label": "TEXT", "label": "TEXT"}),
            ("SQLite_Records(Label)", {"Label": "TEXT"}),
        ]
        for schema, types in cases:
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                generate_create_queries(schema, types)


if __name__ == "__main__":
    unittest.main()

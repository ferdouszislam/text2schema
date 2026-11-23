import unittest

from verifier.verify import verify_schema


class VerificationTests(unittest.TestCase):
    def assert_outcomes(self, result, *, second, third, lossless, preserved):
        expected = {
            "2NF": second,
            "3NF": third,
            "lossless_decomposition": lossless,
            "dependency_preservation": preserved,
        }
        self.assertEqual(result["verified"], all(expected.values()))
        self.assertEqual(set(result["checks"]), set(expected))
        self.assertTrue(result["feedback"].strip())
        for name, passed in expected.items():
            with self.subTest(check=name):
                check = result["checks"][name]
                self.assertEqual(check["passed"], passed)
                self.assertEqual(bool(check["violations"]), not passed)

    def assert_example_joins(self, witness, relations, source_rows, targets, join_order):
        tables = witness["example_tables"]
        expected_tables = {}
        for name, columns in relations.items():
            projection = {tuple(row[column] for column in columns) for row in source_rows}
            expected_tables[name] = [dict(zip(columns, values)) for values in sorted(projection)]
        self.assertEqual(tables, expected_tables)

        traces = witness["join_traces"]
        self.assertEqual(len(traces), len(targets))
        for trace, target in zip(traces, targets):
            self.assertEqual([step["relation"] for step in trace], join_order)
            joined = {}
            for step in trace:
                table = tables[step["relation"]]
                row_number = step["row_number"]
                self.assertGreaterEqual(row_number, 1)
                self.assertLessEqual(row_number, len(table))
                row = table[row_number - 1]
                shared = {column: joined[column] for column in joined.keys() & row.keys()}
                self.assertEqual(step["join_values"], shared)
                self.assertTrue(all(row[column] == value for column, value in shared.items()))
                joined.update(row)
            self.assertEqual(joined, target)

    def test_course_example_preserves_shared_logical_attributes(self):
        schema = """
        Student(<u>Student_Id</u>, Student_Name, Student_DOB)
        Course(<u>Course_Id</u>, Course_Title, Course_Description)
        CoursesTaken(<u>Student_Id</u>, <u>Course_Id</u>, Course_Grade)
        """
        dependencies = """
        [Student_Id] -> [Student_Name, Student_DOB]
        [Course_Id] -> [Course_Title, Course_Description]
        [Student_Id, Course_Id] -> [Course_Grade]
        """
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=True)

    def test_matching_suffixes_do_not_create_a_join(self):
        schema = """
        Student(<u>Student_Id</u>, Student_Name)
        Course(<u>Course_Id</u>, Course_Name)
        """
        dependencies = ["[Student_Id] -> [Student_Name]", "[Course_Id] -> [Course_Name]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=True, third=True, lossless=False, preserved=True)
        witness, = result["checks"]["lossless_decomposition"]["violations"]
        self.assertEqual(witness["join_attributes"], {})
        self.assertEqual(witness["spurious_join_pairs"], [])
        self.assertIn("Cartesian product", result["feedback"])
        self.assert_example_joins(
            witness,
            {"Student": ("Student_Id", "Student_Name"), "Course": ("Course_Id", "Course_Name")},
            list(witness["witness_rows"].values()), [witness["spurious_tuple"]],
            ["Student", "Course"],
        )
        step = witness["join_traces"][0][1]
        self.assertIn(f"Combine with Course row {step['row_number']} by Cartesian product.",
                      witness["message"])

    def test_partial_dependency_on_alternate_candidate_key(self):
        schema = "R(<u>A</u>, <u>B</u>, C, Dependent_Value)"
        dependencies = ["[A, B] -> [C]", "[A, C] -> [B]", "[C] -> [Dependent_Value]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=True)
        self.assertIn("2NF", result["feedback"])
        self.assertIn("Dependent_Value", result["feedback"])

    def test_projected_dependency_implied_via_an_outside_attribute(self):
        schema = """
        R(<u>A</u>, Dependent_Value, <u>C</u>)
        S(<u>A</u>, D)
        T(<u>D</u>, Dependent_Value)
        """
        dependencies = ["[A] -> [D]", "[D] -> [Dependent_Value]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=True)
        self.assertIn("Dependent_Value", result["feedback"])

    def test_transitive_dependency_violates_only_third_normal_form(self):
        result = verify_schema("R(<u>A</u>, B, C)", ["[A] -> [B]", "[B] -> [C]"])
        self.assert_outcomes(result, second=True, third=False, lossless=True, preserved=True)

    def test_feedback_covers_violating_attributes_in_each_relation(self):
        schema = """
        First(<u>A</u>, <u>B</u>, First_Value, Second_Value)
        Second(<u>C</u>, <u>D</u>, Third_Value)
        """
        dependencies = ["[A] -> [First_Value, Second_Value]", "[C] -> [Third_Value]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=False, third=False, lossless=False, preserved=True)
        for attribute in ("First_Value", "Second_Value", "Third_Value"):
            self.assertIn(attribute, result["feedback"])

    def test_third_normal_form_allows_prime_dependent(self):
        result = verify_schema("R(<u>A</u>, <u>B</u>, C)", ["[A, B] -> [C]", "[C] -> [B]"])
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=True)

    def test_dependency_preserving_decomposition_can_be_lossy(self):
        schema = """
        R(<u>A</u>, B)
        S(<u>B</u>, <u>C</u>)
        """
        result = verify_schema(schema, ["[A] -> [B]"])
        self.assert_outcomes(result, second=True, third=True, lossless=False, preserved=True)
        witness, = result["checks"]["lossless_decomposition"]["violations"]
        target = witness["spurious_tuple"]
        rows = witness["witness_rows"]
        self.assertNotIn(target, rows.values())
        self.assertEqual(witness["join_attributes"], {"B": ["R", "S"]})
        self.assertEqual(witness["spurious_join_pairs"], [
            {"relations": ["R", "S"], "join_values": {"B": target["B"]}},
        ])
        self.assertIn(f"Joining R and S on B={target['B']} produces a spurious combination",
                      result["feedback"])
        self.assert_example_joins(witness, {"R": ("A", "B"), "S": ("B", "C")},
                                  list(rows.values()), [target], ["R", "S"])
        second_step = witness["join_traces"][0][1]
        self.assertIn("Source data before decomposition", witness["message"])
        self.assertIn(f"Source row 1: {rows['R']}", witness["message"])
        self.assertIn(f"Source row 2: {rows['S']}", witness["message"])
        self.assertNotIn("Row for ", witness["message"])
        self.assertIn("Example table rows before the join", witness["message"])
        self.assertIn("Join trace for", witness["message"])
        self.assertIn(f"Join S row {second_step['row_number']} on B=0.", witness["message"])
        for name, attributes in (("R", ("A", "B")), ("S", ("B", "C"))):
            self.assertTrue(all(rows[name][attribute] == target[attribute]
                                for attribute in attributes))

    def test_lossy_join_explains_composite_match_and_omits_existing_pair(self):
        schema = """
        Summary(A, B)
        Detail(B, C)
        R(A, B, C)
        S(B, C, D)
        """
        result = verify_schema(schema, [])
        self.assert_outcomes(result, second=True, third=True, lossless=False, preserved=True)
        witness, = result["checks"]["lossless_decomposition"]["violations"]
        target = witness["spurious_tuple"]
        self.assertEqual(witness["join_attributes"], {
            "A": ["Summary", "R"], "B": ["Summary", "Detail", "R", "S"], "C": ["Detail", "R", "S"],
        })
        self.assertEqual(witness["spurious_join_pairs"], [
            {"relations": ["Summary", "S"], "join_values": {"B": target["B"]}},
            {"relations": ["R", "S"], "join_values": {"B": target["B"], "C": target["C"]}},
        ])
        self.assertIn(f"Joining R and S on B={target['B']}, C={target['C']}", result["feedback"])
        # Summary and Detail overlap, but R's source row already combines their values.
        self.assertTrue(all(witness["witness_rows"]["R"][column] == target[column]
                            for column in ("A", "B", "C")))
        self.assert_example_joins(
            witness, {"Summary": ("A", "B"), "Detail": ("B", "C"),
                      "R": ("A", "B", "C"), "S": ("B", "C", "D")},
            list(witness["witness_rows"].values()), [target], ["Summary", "Detail", "R", "S"],
        )

    def test_lossy_join_trace_prefers_a_relation_with_shared_columns(self):
        result = verify_schema("R(A, B)\nS(C, D)\nT(B, C)", [])
        self.assert_outcomes(result, second=True, third=True, lossless=False, preserved=True)
        witness, = result["checks"]["lossless_decomposition"]["violations"]
        self.assert_example_joins(
            witness, {"R": ("A", "B"), "S": ("C", "D"), "T": ("B", "C")},
            list(witness["witness_rows"].values()), [witness["spurious_tuple"]], ["R", "T", "S"],
        )

    def test_lossless_decomposition_can_fail_to_preserve_dependency(self):
        schema = """
        R(<u>A</u>, <u>C</u>)
        S(<u>C</u>, B)
        """
        dependencies = ["[A, B] -> [C]", "[C] -> [B]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=False)
        violation, = result["checks"]["dependency_preservation"]["violations"]
        self.assertEqual(violation["missing_attributes"], ["C"])
        self.assertEqual(violation["relation_columns"], {"R": ["A", "C"], "S": ["B", "C"]})
        first, second = violation["witness_rows"]
        self.assertEqual((first["A"], first["B"]), (second["A"], second["B"]))
        self.assertNotEqual(first["C"], second["C"])
        self.assert_example_joins(violation, {"R": ("A", "C"), "S": ("C", "B")},
                                  [first, second], [first, second], ["R", "S"])
        self.assertEqual(violation["example_tables"], {
            "R": [{"A": 0, "C": 0}, {"A": 0, "C": 1}],
            "S": [{"C": 0, "B": 0}, {"C": 1, "B": 0}],
        })
        self.assertIn("Example table rows before the join", violation["message"])
        self.assertEqual(violation["message"].count("Join trace for"), 2)
        self.assertIn("Join S row 1 on C=0.", violation["message"])
        self.assertIn("Join S row 2 on C=1.", violation["message"])
        self.assertIn(f"Joined row 1: {first}", violation["message"])
        self.assertIn(f"Joined row 2: {second}", violation["message"])
        self.assertIn("The joined rows agree on A=0, B=0 and differ on C (0 versus 1).",
                      violation["message"])

    def test_multiway_decomposition_can_be_lossless_when_each_pair_is_lossy(self):
        schema = """
        R(<u>A</u>, C, <u>D</u>, <u>E</u>)
        S(<u>B</u>, <u>C</u>, D)
        T(<u>A</u>, <u>B</u>, <u>E</u>)
        """
        dependencies = ["[A, E] -> [C]", "[B, C] -> [D, E]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=False)

    def test_preservation_combines_projected_dependencies_across_relations(self):
        schema = """
        R(<u>A</u>, Intermediate)
        S(<u>Intermediate</u>, C)
        """
        dependencies = ["[A] -> [Intermediate, C]", "[Intermediate] -> [C]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=True)

    def test_empty_determinant_can_be_a_partial_dependency(self):
        result = verify_schema("R(<u>A</u>, Constant_Value)", ["[] -> [Constant_Value]"])
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=True)
        self.assertIn("Constant_Value", result["feedback"])

    def test_rejects_attribute_repeated_within_one_relation(self):
        with self.assertRaisesRegex(ValueError, "Student_Id"):
            verify_schema("Student(<u>Student_Id</u>, Student_Id)", [])

    def test_unknown_dependency_attribute_is_an_input_error(self):
        with self.assertRaisesRegex(ValueError, "Couse_Id"):
            verify_schema("Course(<u>Course_Id</u>, Course_Title)", ["[Couse_Id] -> [Course_Title]"])


if __name__ == "__main__":
    unittest.main()

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
        for name, attributes in (("R", ("A", "B")), ("S", ("B", "C"))):
            self.assertTrue(all(rows[name][attribute] == target[attribute] for attribute in attributes))

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

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
        Student(<u>Student_StudentId</u>, StudentName, StudentDOB)
        Course(<u>Course_CourseId</u>, CourseTitle, CourseDescription)
        CoursesTaken(<u>CoursesTaken_StudentId</u>, <u>CoursesTaken_CourseId</u>, CourseGrade)
        """
        dependencies = """
        [StudentId] -> [StudentName, StudentDOB]
        [CourseId] -> [CourseTitle, CourseDescription]
        [StudentId, CourseId] -> [CourseGrade]
        """
        aliases = {
            "Student_StudentId": "StudentId",
            "CoursesTaken_StudentId": "StudentId",
            "Course_CourseId": "CourseId",
            "CoursesTaken_CourseId": "CourseId",
        }
        result = verify_schema(schema, dependencies, attribute_aliases=aliases)
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=True)

    def test_matching_physical_suffixes_do_not_create_a_join(self):
        schema = """
        LeftPart(<u>LeftPart_Id</u>, LeftValue)
        RightPart(<u>RightPart_Id</u>, RightValue)
        """
        dependencies = ["[LeftPart_Id] -> [LeftValue]", "[RightPart_Id] -> [RightValue]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=True, third=True, lossless=False, preserved=True)

    def test_partial_dependency_on_alternate_candidate_key(self):
        schema = "R(<u>A</u>, <u>B</u>, C, DependentValue)"
        dependencies = ["[A, B] -> [C]", "[A, C] -> [B]", "[C] -> [DependentValue]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=True)
        self.assertIn("2NF", result["feedback"])
        self.assertIn("DependentValue", result["feedback"])

    def test_projected_dependency_implied_via_an_outside_attribute(self):
        schema = """
        R(<u>A</u>, DependentValue, <u>C</u>)
        S(<u>S_A</u>, D)
        T(<u>T_D</u>, T_DependentValue)
        """
        dependencies = ["[A] -> [D]", "[D] -> [DependentValue]"]
        aliases = {"S_A": "A", "T_D": "D", "T_DependentValue": "DependentValue"}
        result = verify_schema(schema, dependencies, attribute_aliases=aliases)
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=True)
        self.assertIn("DependentValue", result["feedback"])

    def test_transitive_dependency_violates_only_third_normal_form(self):
        result = verify_schema("R(<u>A</u>, B, C)", ["[A] -> [B]", "[B] -> [C]"])
        self.assert_outcomes(result, second=True, third=False, lossless=True, preserved=True)

    def test_feedback_covers_violating_attributes_in_each_relation(self):
        schema = """
        First(<u>A</u>, <u>B</u>, FirstValue, SecondValue)
        Second(<u>C</u>, <u>D</u>, ThirdValue)
        """
        dependencies = ["[A] -> [FirstValue, SecondValue]", "[C] -> [ThirdValue]"]
        result = verify_schema(schema, dependencies)
        self.assert_outcomes(result, second=False, third=False, lossless=False, preserved=True)
        for attribute in ("FirstValue", "SecondValue", "ThirdValue"):
            self.assertIn(attribute, result["feedback"])

    def test_third_normal_form_allows_prime_dependent(self):
        result = verify_schema("R(<u>A</u>, <u>B</u>, C)", ["[A, B] -> [C]", "[C] -> [B]"])
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=True)

    def test_dependency_preserving_decomposition_can_be_lossy(self):
        schema = """
        R(<u>A</u>, B)
        S(<u>S_B</u>, <u>C</u>)
        """
        result = verify_schema(schema, ["[A] -> [B]"], attribute_aliases={"S_B": "B"})
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
        S(<u>S_C</u>, B)
        """
        dependencies = ["[A, B] -> [C]", "[C] -> [B]"]
        result = verify_schema(schema, dependencies, attribute_aliases={"S_C": "C"})
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=False)
        violation, = result["checks"]["dependency_preservation"]["violations"]
        self.assertEqual(violation["missing_attributes"], ["C"])
        self.assertEqual(violation["relation_columns"], {"R": ["A", "C"], "S": ["B", "S_C"]})
        first, second = violation["witness_rows"]
        self.assertEqual((first["A"], first["B"]), (second["A"], second["B"]))
        self.assertNotEqual(first["C"], second["C"])

    def test_multiway_decomposition_can_be_lossless_when_each_pair_is_lossy(self):
        schema = """
        R(<u>A</u>, C, <u>D</u>, <u>E</u>)
        S(<u>B</u>, <u>S_C</u>, S_D)
        T(<u>T_A</u>, <u>T_B</u>, <u>T_E</u>)
        """
        dependencies = ["[A, E] -> [C]", "[B, C] -> [D, E]"]
        aliases = {"S_C": "C", "S_D": "D", "T_A": "A", "T_B": "B", "T_E": "E"}
        result = verify_schema(schema, dependencies, attribute_aliases=aliases)
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=False)

    def test_preservation_combines_projected_dependencies_across_relations(self):
        schema = """
        R(<u>A</u>, Intermediate)
        S(<u>S_Intermediate</u>, C)
        """
        dependencies = ["[A] -> [Intermediate, C]", "[Intermediate] -> [C]"]
        result = verify_schema(
            schema, dependencies, attribute_aliases={"S_Intermediate": "Intermediate"}
        )
        self.assert_outcomes(result, second=True, third=True, lossless=True, preserved=True)

    def test_empty_determinant_can_be_a_partial_dependency(self):
        result = verify_schema("R(<u>A</u>, ConstantValue)", ["[] -> [ConstantValue]"])
        self.assert_outcomes(result, second=False, third=False, lossless=True, preserved=True)
        self.assertIn("ConstantValue", result["feedback"])

    def test_unknown_dependency_attribute_is_an_input_error(self):
        with self.assertRaisesRegex(ValueError, "CouseId"):
            verify_schema("Course(<u>CourseId</u>, Title)", ["[CouseId] -> [Title]"])


if __name__ == "__main__":
    unittest.main()

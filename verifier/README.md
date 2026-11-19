# Z3 schema verifier

The verifier checks a proposed relational schema for second normal form (2NF), third normal form (3NF), lossless decomposition, and dependency preservation. It uses the supplied functional dependencies (FDs) as the rules of the original, universal relation. The universal relation's attributes are the union of the proposed relations' logical attributes.

## Run the verifier

From the project root, activate the shared Python 3.11+ environment and install the dependencies from the root [requirements file](../requirements.txt). See the [project setup instructions](../README.md) to create the environment.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Call `verify_schema` from Python with the schema declarations and the original FDs. This example qualifies the repeated ID column names with their table names. The alias mapping identifies the logical attributes shared by the tables, and the FDs use these stable logical names.

```python
from verifier.verify import verify_schema

schema = """
Student(<u>Student.StudentId</u>, StudentName, StudentDOB)
Course(<u>Course.CourseId</u>, CourseTitle, CourseDescription)
CoursesTaken(<u>CoursesTaken.StudentId</u>, <u>CoursesTaken.CourseId</u>, CourseGrade)
"""

dependencies = [
    "[StudentId] -> [StudentName, StudentDOB]",
    "[CourseId] -> [CourseTitle, CourseDescription]",
    "[StudentId, CourseId] -> [CourseGrade]",
]

aliases = {
    "Student.StudentId": "StudentId",
    "CoursesTaken.StudentId": "StudentId",
    "Course.CourseId": "CourseId",
    "CoursesTaken.CourseId": "CourseId",
}

result = verify_schema(schema, dependencies, attribute_aliases=aliases)
print(result["feedback"])  # Verified.
```

Run the verifier tests from the project root.

```bash
python -m unittest discover -s verifier/tests
```

## Input and output

- Give one `Relation(Attribute, <u>PrimaryKeyAttribute</u>)` declaration per line. Omit section headings from both inputs. Blank lines are allowed. Wrap each primary key column in `<u>` and `</u>`. Each physical attribute name must be unique across the schema. Names are case-sensitive. They can contain letters, digits, or underscores, starting with a letter or underscore. The same rule applies to each segment of a qualified name such as `Student.StudentId`.
- Pass FDs as a sequence of strings or as one string with one FD per line. Use `[A, B] -> [C, D]`, where each identifier names a declared column or a logical attribute. An exact declared column name takes precedence and resolves through its alias, if present. Use `[] -> [A]` when every row must have the same value for `A`.
- Supply aliases for columns in different relations that represent a shared logical attribute. Each alias maps an exact declared column name to a logical name. An unmapped column keeps its declared name as its logical name. For example, `Customer.Name` and `Course.Name` represent distinct logical attributes by default, even though they share the suffix `Name`.
- The verifier retains the primary key markers as schema metadata. It derives candidate keys for the normal-form checks from the FDs, including alternate keys. Supply the FDs that express the intended key constraints.

The returned dictionary is JSON-serializable and contains `verified`, a Boolean that is true when all four checks pass, and `feedback`, the human-readable result. A passing result reads `Verified.` A failing result starts with `Not verified.` and explains the violations. For structured handling, look up each rule in `result["checks"]` using `2NF`, `3NF`, `lossless_decomposition`, or `dependency_preservation`. Each entry contains `passed` and `violations`. Malformed input or an unknown attribute raises `ValueError` so the caller can correct the input. An inconclusive solver result raises `RuntimeError`.

### Example failing output

This version of `CoursesTaken` stores `CourseTitle` alongside `CourseGrade`. `CourseId` alone determines the title, while the grade depends on both key columns.

```python
from verifier.verify import verify_schema

schema = "CoursesTaken(<u>StudentId</u>, <u>CourseId</u>, CourseTitle, CourseGrade)"
dependencies = [
    "[CourseId] -> [CourseTitle]",
    "[StudentId, CourseId] -> [CourseGrade]",
]

result = verify_schema(schema, dependencies)
print(result["feedback"])
```

```text
Not verified.
2NF — CoursesTaken: [CourseId] -> [CourseTitle] is a partial dependency. The determinant is a proper subset of the following candidate keys: [CourseId, StudentId] (declared primary key). CourseTitle is non-prime.
3NF — CoursesTaken: [CourseId] -> [CourseTitle] follows from the functional dependencies. The determinant cannot determine [CourseGrade, StudentId] in this relation, and CourseTitle belongs to no candidate key.
```

## Use in the project

The planned workflow first extracts the original FDs from the database specification and generates a candidate schema. Preprocessing assigns unique names to the candidate columns and records which columns represent the same logical attribute. Pass the resulting inputs to `verify_schema`. Use `result["verified"]` to decide whether to accept the candidate. On a failed check, pass `result["feedback"]` to the LLM so it can revise the schema. Use stable logical identifiers in the FDs so the same rules can be checked against each revised schema and its alias mapping.

See [Verification explained](VERIFICATION-EXPLAINED.md) for the rules and how Z3 checks them.

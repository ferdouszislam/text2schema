# Z3 schema verifier

The verifier checks a proposed relational schema for second normal form (2NF), third normal form (3NF), lossless decomposition, and dependency preservation. It uses the supplied functional dependencies (FDs) as the rules of the original, universal relation. The universal relation's attributes are the union of the proposed relations' logical attributes.

## Run the verifier

From the project root, activate the shared Python 3.11+ environment and install the dependencies from the root [requirements file](../requirements.txt). See the [project setup instructions](../README.md) to create the environment.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Call `verify_schema` from Python with the schema declarations and the original FDs. In this example, `Student_Id` and `Course_Id` keep the same names wherever they appear because they represent shared attributes.

```python
from verifier.verify import verify_schema

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

result = verify_schema(schema, dependencies)
print(result["feedback"])  # Verified.
```

Run the verifier tests from the project root.

```bash
python -m unittest discover -s verifier/tests
```

## Input and output

- Give one `Relation(Attribute, <u>Key_Attribute</u>)` declaration per line. Omit section headings from both inputs. Blank lines are allowed. Wrap each primary key column in `<u>` and `</u>`. A name can appear once per relation. Names are case-sensitive.
- Reuse the exact same name for a shared logical attribute. Give distinct attributes distinct names. For example, use `Student_Name` and `Course_Name` for two unrelated name columns.
- Pass FDs as a sequence of strings or as one string with one FD per line. Use `[A, B] -> [C, D]` with the same attribute names used in the schema. Use `[] -> [A]` when every row must have the same value for `A`.
- The verifier retains the primary key markers as schema metadata. It derives candidate keys for the normal-form checks from the FDs, including alternate keys. Supply the FDs that express the intended key constraints.

The returned dictionary is JSON-serializable and contains `verified`, a Boolean that is true when all four checks pass, and `feedback`, the human-readable result. A passing result reads `Verified.` A failing result starts with `Not verified.` and explains the violations. For structured handling, look up each rule in `result["checks"]` using `2NF`, `3NF`, `lossless_decomposition`, or `dependency_preservation`. Each entry contains `passed` and `violations`. Malformed input or an unknown attribute raises `ValueError` so the caller can correct the input. An inconclusive solver result raises `RuntimeError`.

### Example failing output

This version of `CoursesTaken` stores `Course_Title` alongside `Course_Grade`. `Course_Id` alone determines the title, while the grade depends on both key columns.

```python
from verifier.verify import verify_schema

schema = "CoursesTaken(<u>Student_Id</u>, <u>Course_Id</u>, Course_Title, Course_Grade)"
dependencies = [
    "[Course_Id] -> [Course_Title]",
    "[Student_Id, Course_Id] -> [Course_Grade]",
]

result = verify_schema(schema, dependencies)
print(result["feedback"])
```

```text
Not verified.
2NF — CoursesTaken: [Course_Id] -> [Course_Title] is a partial dependency. The determinant is a proper subset of the following candidate keys: [Course_Id, Student_Id] (declared primary key). Course_Title is non-prime.
3NF — CoursesTaken: [Course_Id] -> [Course_Title] follows from the functional dependencies. The determinant cannot determine [Course_Grade, Student_Id] in this relation, and Course_Title belongs to no candidate key.
```

## Use in the project

The planned workflow first extracts the original FDs from the database specification and generates a candidate schema. Use the same name for each logical attribute in the FDs and every candidate relation that contains it. Pass the schema and FDs to `verify_schema`. Use `result["verified"]` to decide whether to accept the candidate. On a failed check, pass `result["feedback"]` to the LLM so it can revise the schema. Keep the attribute names stable across revisions so the same FDs can be checked again.

See [Verification explained](VERIFICATION-EXPLAINED.md) for the rules and how Z3 checks them.

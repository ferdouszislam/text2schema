# Generate CREATE queries

`generate_create_queries` converts a relational schema and its attribute types into SQLite `CREATE TABLE` statements. Call it from Python to get SQL strings you can save or execute with a SQLite connection. The function uses only the Python standard library.

## Generate SQL from Python

Run this example from the project root.

```python
from create_query_generator.create_query_generator import generate_create_queries

schema = """
Student(<u>Student_Id</u>, Student_Name, Student_DOB)
Course(<u>Course_Id</u>, Course_Title, Course_Description)
CoursesTaken(<u>Student_Id</u>, <u>Course_Id</u>, Course_Grade)
"""

attribute_types = {
    "Student_Id": "INTEGER",
    "Student_Name": "TEXT",
    "Student_DOB": "DATE",
    "Course_Id": "INTEGER",
    "Course_Title": "VARCHAR(255)",
    "Course_Description": "TEXT",
    "Course_Grade": "TEXT",
}

queries = generate_create_queries(schema, attribute_types)
print("\n\n".join(queries))
```

The final statement in `queries` is the one for `CoursesTaken`.

```sql
CREATE TABLE "CoursesTaken" (
    "Student_Id" INTEGER NOT NULL,
    "Course_Id" INTEGER NOT NULL,
    "Course_Grade" TEXT,
    PRIMARY KEY ("Student_Id", "Course_Id")
);
```

## Inputs and return value

- Give one `Relation(Column, <u>Key</u>)` declaration per line. Wrap each primary key column in `<u>` and `</u>`, including every column of a composite key. A name can appear once per relation. Names are case-sensitive in the schema and type mapping.
- Reuse the exact name when an attribute appears in several relations, as with `Student_Id` above. Give unrelated attributes distinct names, such as `Student_Name` and `Course_Name`.
- Supply `attribute_types` as a mapping from each attribute name to a SQL type string, such as `INTEGER`, `TEXT`, `DATE`, `DATETIME`, `VARCHAR(255)`, or `DECIMAL(10, 2)`. A single entry supplies the type wherever the attribute appears. Supported types accept up to two nonnegative integer arguments. [Supported type names](create_query_generator.py)

The function returns a list with one semicolon-terminated statement per relation, in schema order. It preserves and quotes the declared table and column names, adds `NOT NULL` to marked key columns, and emits a table-level `PRIMARY KEY` for each declared key. Invalid schema text or type assignments raise `ValueError`. [Generation explained](GENERATION-EXPLAINED.md)

## Run the generator tests

```bash
python -m unittest discover -s create_query_generator/tests
```

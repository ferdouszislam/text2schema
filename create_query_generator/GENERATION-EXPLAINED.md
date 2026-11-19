# How CREATE query generation works

`generate_create_queries` takes a relational schema and a mapping of attribute names to SQL types. It uses the shared relational schema parser to read each relation's name, columns, and `<u>` primary key markers.

## Resolve types

Each attribute name identifies one logical attribute. For example, when `Student` and `CoursesTaken` both declare `Student_Id`, a single `Student_Id` entry in the type mapping supplies the type for both columns. The parser also rejects a repeated column name within a single relation.

The generator requires a type for every declared attribute name and checks each type against the supported names. It normalizes case, spacing, and leading zeros in numeric arguments. For example, ` decimal (010, 02) ` becomes `DECIMAL(10, 2)`. Validation completes before the generator returns any statements.

## Write the table definitions

For each relation, the generator emits its columns in declaration order. It double-quotes table and column identifiers so a name such as `Order` can be used as an identifier. It adds each column's resolved type and emits `NOT NULL` on marked key columns. If any columns are marked, one table-level `PRIMARY KEY` clause lists them in column order. The explicit `NOT NULL` declarations cover ordinary SQLite tables where some primary keys can otherwise store `NULL`. [SQLite CREATE TABLE documentation](https://www.sqlite.org/lang_createtable.html#the_primary_key)

SQLite compares identifiers case-insensitively for ASCII letters. The generator checks for conflicting table names and for conflicting column names within each table. It also checks for SQLite's reserved `sqlite_` table-name prefix.

The column type declarations use SQLite's normal type affinity rules. For example, `VARCHAR(255)` gives the column text affinity. The supplied lengths and precisions appear in the DDL and have the meaning SQLite gives them. [SQLite datatype documentation](https://www.sqlite.org/datatype3.html#type_affinity)

The function returns SQL strings. The caller selects where to execute them. The input's `<u>` markers supply the primary key constraints. A foreign-key clause requires separate information about which table and key a column references.

See the [generator README](README.md) for an end-to-end example.

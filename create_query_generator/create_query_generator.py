"""Generate SQLite-compatible CREATE TABLE statements from a relational schema."""

from collections.abc import Mapping
import re
from string import ascii_lowercase, ascii_uppercase

from util.relational_schema import parse_relational_schema


SUPPORTED_TYPE_NAMES = frozenset({
    "BIGINT", "BLOB", "BOOL", "BOOLEAN", "CHAR", "CHARACTER", "CHARACTER VARYING",
    "CLOB", "DATE", "DATETIME", "DEC", "DECIMAL", "DOUBLE", "DOUBLE PRECISION",
    "FLOAT", "INT", "INT2", "INT8", "INTEGER", "JSON", "MEDIUMINT", "NATIVE CHARACTER",
    "NCHAR", "NUMERIC", "NVARCHAR", "REAL", "SMALLINT", "TEXT", "TIME", "TIMESTAMP",
    "TINYINT", "UNSIGNED BIG INT", "UUID", "VARBINARY", "VARCHAR", "VARYING CHARACTER",
})
_TYPE = re.compile(
    r"([A-Za-z][A-Za-z0-9]*(?:[ \t]+[A-Za-z][A-Za-z0-9]*)*)"
    r"(?:[ \t]*\([ \t]*([0-9]+)(?:[ \t]*,[ \t]*([0-9]+))?[ \t]*\))?"
)
_SQLITE_LOWER = str.maketrans(ascii_uppercase, ascii_lowercase)


def _normalize_type(value: str, attribute: str) -> str:
    match = _TYPE.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"Invalid SQL type {value!r} for {attribute!r}. Give a type declaration only.")
    base = " ".join(match[1].upper().split())
    if base not in SUPPORTED_TYPE_NAMES:
        raise ValueError(f"Unsupported SQL type {value!r} for {attribute!r}.")
    arguments = [argument.lstrip("0") or "0" for argument in match.groups()[1:]
                 if argument is not None]
    if arguments:
        return f"{base}({', '.join(arguments)})"
    return base


def normalize_attribute_types(attribute_types: Mapping[str, str], attributes: set[str]) -> dict[str, str]:
    """Validate type coverage for the given attributes and normalize the declarations."""
    if not isinstance(attribute_types, Mapping):
        raise ValueError("Attribute types must map attribute names to SQL type strings.")
    types = {}
    for attribute, value in attribute_types.items():
        if not isinstance(attribute, str) or attribute not in attributes:
            raise ValueError(f"SQL type supplied for unknown attribute {attribute!r}.")
        types[attribute] = _normalize_type(value, attribute)
    missing = attributes - types.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Missing SQL types for attributes: {names}.")
    return types


def _validate_sqlite_names(relations):
    tables = set()
    for relation in relations:
        table = relation.name.translate(_SQLITE_LOWER)
        if table.startswith("sqlite_"):
            raise ValueError(f"Table name {relation.name!r} uses SQLite's reserved sqlite_ prefix.")
        if table in tables:
            raise ValueError(f"Table name {relation.name!r} conflicts with another SQLite table name.")
        tables.add(table)
        columns = set()
        for declared in relation.columns:
            column = declared.translate(_SQLITE_LOWER)
            if column in columns:
                raise ValueError(f"Column {declared!r} conflicts with another SQLite column in {relation.name!r}.")
            columns.add(column)


def generate_create_queries(
    relational_schema: str,
    attribute_types: Mapping[str, str],
) -> list[str]:
    """Return one SQLite-compatible CREATE TABLE statement per relation.

    ``relational_schema`` has one ``Relation(A, <u>B</u>)`` declaration per
    line. Names are case-sensitive and unique within each relation. Use the
    same name in different relations for the same attribute. Use distinct
    names for different attributes, such as ``Student_Name`` and
    ``Course_Name``. Each underlined column belongs to the table's primary key.

    ``attribute_types`` maps each distinct column name to a SQL type string
    such as ``INTEGER``, ``VARCHAR(255)``, or ``DECIMAL(10, 2)``. A name that
    occurs in multiple relations uses the same type in each. Type syntax
    accepts the supported type names and optional numeric arguments.

    The statements preserve relation and column order, quote the declared
    identifiers, and end with semicolons. A declared key is emitted as one
    table-level PRIMARY KEY, with NOT NULL on its columns. The function
    returns SQL text for the caller to save or execute. Invalid schema, type
    mappings, or SQLite names raise ValueError.
    """
    relations, attributes = parse_relational_schema(relational_schema)
    _validate_sqlite_names(relations)
    types = normalize_attribute_types(attribute_types, attributes)

    statements = []
    for relation in relations:
        clauses = []
        key_columns = []
        for attribute in relation.columns:
            identifier = f'"{attribute}"'
            column = f"    {identifier} {types[attribute]}"
            if attribute in relation.primary_key:
                column += " NOT NULL"
                key_columns.append(identifier)
            clauses.append(column)
        if key_columns:
            clauses.append(f"    PRIMARY KEY ({', '.join(key_columns)})")
        body = ",\n".join(clauses)
        statements.append(f'CREATE TABLE "{relation.name}" (\n{body}\n);')
    return statements

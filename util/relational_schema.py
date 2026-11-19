"""Shared input format for the verifier and CREATE TABLE generator."""

from dataclasses import dataclass
import re


_NAME = re.compile(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*")
_RELATION = re.compile(r"([^()]+)\(([^()]*)\)")


@dataclass(frozen=True)
class Relation:
    name: str
    columns: tuple[str, ...]
    primary_key: frozenset[str]


def parse_identifier(value: str, location: str) -> str:
    value = value.strip()
    if not _NAME.fullmatch(value):
        raise ValueError(f"{location}: invalid identifier {value!r}.")
    return value


def parse_relational_schema(schema_text: str) -> tuple[list[Relation], set[str]]:
    """Return the parsed relations and the union of their attribute names."""
    if not isinstance(schema_text, str):
        raise ValueError("Relational schema must be text with one relation per line.")

    relations = []
    relation_names = set()
    attributes = set()
    for line_number, line in enumerate(schema_text.splitlines(), start=1):
        if not line.strip():
            continue
        location = f"Schema line {line_number}"
        match = _RELATION.fullmatch(line.strip())
        if match is None:
            raise ValueError(f"{location}: expected Relation(Column, <u>Key</u>).")
        name = parse_identifier(match[1], location)
        if name in relation_names:
            raise ValueError(f"{location}: duplicate relation {name!r}.")
        relation_names.add(name)
        columns = []
        key = set()
        for column in match[2].split(","):
            column = column.strip()
            is_key = column.startswith("<u>") and column.endswith("</u>")
            attribute = parse_identifier(column[3:-4] if is_key else column, location)
            if attribute in columns:
                raise ValueError(f"{location}: duplicate column {attribute!r} in relation {name!r}.")
            columns.append(attribute)
            if is_key:
                key.add(attribute)
        attributes.update(columns)
        relations.append(Relation(name, tuple(columns), frozenset(key)))
    if not relations:
        raise ValueError("Relational schema must contain at least one relation.")
    return relations, attributes

"""Extract CREATE TABLE names and compare generated and target schemas."""

from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import re

from dataset.RSchema.analysis.scripts.analyze_rschema import scan, split_sql


_TRIVIA_PATTERN = r"(?:\s|--[^\n]*(?:\n|$)|/\*.*?\*/)*"
_TRIVIA = re.compile(_TRIVIA_PATTERN, re.S)
_CREATE_TABLE = re.compile(
    rf"CREATE\b{_TRIVIA_PATTERN}(?:(?:TEMP|TEMPORARY)\b{_TRIVIA_PATTERN})?"
    rf"TABLE\b{_TRIVIA_PATTERN}(?:IF\b{_TRIVIA_PATTERN}NOT\b{_TRIVIA_PATTERN}"
    rf"EXISTS\b{_TRIVIA_PATTERN})?",
    re.I | re.S,
)
_IDENTIFIER = re.compile(
    r'''"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]|'(?:[^']|'')*'|'''
    r"[A-Za-z_\u0080-\U0010ffff][A-Za-z_0-9$\u0080-\U0010ffff]*"
)
_TABLE_CONSTRAINT = re.compile(
    rf"CONSTRAINT\b|(?:PRIMARY\b{_TRIVIA_PATTERN}KEY\b|FOREIGN\b{_TRIVIA_PATTERN}"
    rf"KEY\b|CHECK\b|UNIQUE\b){_TRIVIA_PATTERN}\(",
    re.I | re.S,
)
_TABLE_OPTIONS = re.compile(
    rf"(?:WITHOUT\b{_TRIVIA_PATTERN}ROWID|STRICT)(?:{_TRIVIA_PATTERN},"
    rf"{_TRIVIA_PATTERN}(?:WITHOUT\b{_TRIVIA_PATTERN}ROWID|STRICT))?{_TRIVIA_PATTERN}",
    re.I | re.S,
)

Schema = Mapping[str, Sequence[str]]
NamePair = tuple[str, str]
ColumnPair = tuple[str, str, str, str]
Judge = Callable[[str, Sequence[NamePair]], Sequence[int]]


def _strip_trivia(sql: str) -> str:
    return sql[_TRIVIA.match(sql).end():]


def _read_identifier(sql: str) -> tuple[str, str]:
    sql = _strip_trivia(sql)
    match = _IDENTIFIER.match(sql)
    if match is None:
        raise ValueError(f"Expected a SQL identifier near {sql[:100]!r}")
    token = match[0]
    quote = token[0]
    if quote == "[":
        name = token[1:-1]
    elif quote in ('"', "'", "`"):
        name = token[1:-1].replace(quote * 2, quote)
    else:
        name = token
    return name, _strip_trivia(sql[match.end():])


def extract_schema(sql: str | Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Read table and declared column names from a script or a list of CREATE statements."""
    scripts = (sql,) if isinstance(sql, str) else sql
    schema = {}
    for script in scripts:
        for statement in split_sql(script, ";"):
            statement = _strip_trivia(statement)
            if not statement:
                continue
            create = _CREATE_TABLE.match(statement)
            if create is None:
                raise ValueError(f"Expected CREATE TABLE near {statement[:100]!r}")
            table, definition = _read_identifier(statement[create.end():])
            if definition.startswith("."):
                table, definition = _read_identifier(definition[1:])
            if not definition.startswith("("):
                raise ValueError(f"Expected a column list for table {table!r}")
            close = next(i for i, char, depth in scan(definition) if char == ")" and depth == 1)
            options = _strip_trivia(definition[close + 1:])
            if options and not _TABLE_OPTIONS.fullmatch(options):
                raise ValueError(f"Unsupported CREATE TABLE options for {table!r}: {options!r}")

            columns = []
            for declaration in split_sql(definition[1:close]):
                declaration = _strip_trivia(declaration)
                if declaration and not _TABLE_CONSTRAINT.match(declaration):
                    column, _ = _read_identifier(declaration)
                    columns.append(column)
            if not columns or len(columns) != len(set(columns)):
                raise ValueError(f"Missing or duplicate column names in table {table!r}")
            if table in schema:
                raise ValueError(f"Duplicate CREATE TABLE name {table!r}")
            schema[table] = tuple(columns)
    return schema


@dataclass
class _NameMatches:
    exact: list[NamePair]
    remaining_generated: dict[str, None]
    remaining_target: dict[str, None]
    similar: list[NamePair] = field(default_factory=list)


def _exact_matches(generated: Sequence[str], target: Sequence[str]) -> _NameMatches:
    matches = _NameMatches([], dict.fromkeys(generated), dict.fromkeys(target))
    for normalize in (lambda name: name, str.lower, lambda name: name.replace("_", "").lower()):
        targets = defaultdict(deque)
        for name in matches.remaining_target:
            targets[normalize(name)].append(name)
        for name in tuple(matches.remaining_generated):
            candidates = targets.get(normalize(name))
            if candidates:
                target_name = candidates.popleft()
                matches.exact.append((name, target_name))
                del matches.remaining_generated[name]
                del matches.remaining_target[target_name]
    return matches


def _match_similar(kind: str, matches: Sequence[_NameMatches], judge: Judge) -> None:
    pending = [(match, set()) for match in matches if match.remaining_generated and match.remaining_target]
    while pending:
        requests = []
        next_pending = []
        for match, checked in pending:
            targets_in_round = set()
            for generated in match.remaining_generated:
                for target in match.remaining_target:
                    pair = (generated, target)
                    if pair not in checked and target not in targets_in_round:
                        checked.add(pair)
                        targets_in_round.add(target)
                        requests.append((match, pair))
                        break
            if targets_in_round:
                next_pending.append((match, checked))
        if not requests:
            break
        decisions = judge(kind, [pair for _, pair in requests])
        if len(decisions) != len(requests) or any(decision not in (0, 1) for decision in decisions):
            raise ValueError(f"Expected one binary similarity decision per {kind} name pair")
        for (match, (generated, target)), decision in zip(requests, decisions):
            if decision == 1:
                match.similar.append((generated, target))
                del match.remaining_generated[generated]
                del match.remaining_target[target]
        pending = next_pending


def _metric(target_count: int, exact: list, similarity: list | None) -> dict:
    denominator = target_count or 1
    return {
        "target_count": target_count,
        "exact_count": len(exact),
        "similarity_count": len(similarity) if similarity is not None else None,
        "exact_pct": 100 * len(exact) / denominator,
        "similarity_pct": 100 * len(similarity) / denominator if similarity is not None else None,
        "exact_pairs": exact,
        "similarity_pairs": similarity,
    }


def score_schema_pairs(cases: Sequence[tuple[Schema, Schema]], judge: Judge | None = None) -> list[dict]:
    """Score (generated, target) schemas in order, pooling optional judge calls."""
    tables = [_exact_matches(tuple(generated), tuple(target)) for generated, target in cases]
    if judge is not None:
        _match_similar("table", tables, judge)

    columns = [
        [(source, reference, _exact_matches(generated[source], target[reference]))
         for source, reference in table_matches.exact + table_matches.similar]
        for (generated, target), table_matches in zip(cases, tables)
    ]
    if judge is not None:
        _match_similar("column", [match for schema in columns for _, _, match in schema], judge)

    scores = []
    for (_, target), table_matches, column_matches in zip(cases, tables, columns):
        exact_columns: list[ColumnPair] = []
        similarity_columns: list[ColumnPair] = []
        exact_tables = set(table_matches.exact)
        for source, reference, matches in column_matches:
            exact = [(source, left, reference, right) for left, right in matches.exact]
            if (source, reference) in exact_tables:
                exact_columns.extend(exact)
            similarity_columns.extend(exact)
            similarity_columns.extend((source, left, reference, right) for left, right in matches.similar)
        scores.append({
            "tables": _metric(len(target), table_matches.exact,
                              table_matches.exact + table_matches.similar if judge is not None else None),
            "columns": _metric(sum(map(len, target.values())), exact_columns,
                               similarity_columns if judge is not None else None),
        })
    return scores

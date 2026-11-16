#!/usr/bin/env python3
"""Record exact SQLite errors for every RSchema example and CREATE statement.

Run the original complete SQL answer (stopping at the first failure), then scan
every unchanged statement in a separate database, continuing after failures to
expose additional failing statements. No source fixes or tuple inserts are made.
"""

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import platform
import re
import sqlite3

from analyze_rschema import CREATE, load_jsonl, scan, unquote

ANALYSIS_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]


def error_info(error):
    return {
        'error': str(error),
        'sqlite_errorcode': getattr(error, 'sqlite_errorcode', None),
        'sqlite_errorname': getattr(error, 'sqlite_errorname', None),
    }


def statement_ranges(sql):
    """Retain exact source substrings and positions; never reserialize SQL."""
    ends = [i + 1 for i, c, depth in scan(sql) if c == ';' and depth == 0]
    if not ends or ends[-1] != len(sql):
        ends.append(len(sql))
    start = 0
    statements = []
    for end in ends:
        raw = sql[start:end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        if right > left:
            begin, finish = start + left, start + right
            text = sql[begin:finish]
            match = CREATE.match(text)
            if not match:
                raise ValueError(f'Unsupported SQL statement: {text[:100]}')
            statements.append({
                'statement_index': len(statements) + 1,
                'table': unquote(match[1]),
                'sql_start_line': sql.count('\n', 0, begin) + 1,
                'sql_end_line': sql.count('\n', 0, finish - 1) + 1,
                'sql_start_offset': begin,
                'sql_end_offset': finish,
                'sql': text,
            })
        start = end
    # Independent boundary check for the one-CREATE-header-per-line release.
    headers = list(re.finditer(r'^CREATE\s+TABLE\b', sql, re.M | re.I))
    if [m.start() for m in headers] != [s['sql_start_offset'] for s in statements]:
        raise AssertionError('Statement scanner disagrees with source CREATE headers')
    return statements


def new_database():
    conn = sqlite3.connect(':memory:')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def inspect_example(source_line, row):
    sql = row['answer']
    parts = statement_ranges(sql)
    original = {'status': 'ok', 'error': '', 'sqlite_errorcode': None, 'sqlite_errorname': None}
    conn = new_database()
    try:
        try:
            conn.executescript(sql)
        except sqlite3.Error as error:
            original = dict(status='error', **error_info(error))
    finally:
        conn.close()

    # This second run diagnoses all statements, including ones the original
    # executescript never reaches. Earlier successful statements remain present.
    results = []
    conn = new_database()
    try:
        for statement in parts:
            outcome = dict(source_line=source_line, id=row['id'], **statement,
                           status='ok', error='', sqlite_errorcode=None, sqlite_errorname=None)
            try:
                conn.execute(statement['sql'])
            except sqlite3.Error as error:
                outcome.update(status='error', **error_info(error))
            results.append(outcome)
    finally:
        conn.close()

    failures = [s for s in results if s['status'] == 'error']
    if (original['status'] == 'error') != bool(failures):
        raise AssertionError(f'Whole-script/statement outcome mismatch at source line {source_line}')
    first = failures[0] if failures else None
    if first and original['sqlite_errorcode'] != first['sqlite_errorcode']:
        raise AssertionError(f'First error code mismatch at source line {source_line}')
    for statement in results:
        statement['first_error_in_original'] = bool(first and statement['statement_index'] == first['statement_index'])
        statement['reached_in_original'] = first is None or statement['statement_index'] <= first['statement_index']
    schema = dict(
        source_line=source_line, id=row['id'], original_status=original['status'],
        original_error=original['error'], sqlite_errorcode=original['sqlite_errorcode'],
        sqlite_errorname=original['sqlite_errorname'], statements=len(results),
        failing_statements=len(failures), first_failed_statement=first['statement_index'] if first else '',
        first_failed_table=first['table'] if first else '',
        first_sql_start_line=first['sql_start_line'] if first else '',
        first_sql_end_line=first['sql_end_line'] if first else '',
    )
    return schema, results


def write_csv(path, records):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)


def json_write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def write_report(path, summary, schemas, statements):
    failed_schemas = [r for r in schemas if r['original_status'] == 'error']
    failed_statements = [s for s in statements if s['status'] == 'error']
    lines = [
        '# Exact SQL execution errors by example and table', '',
        f"Tested **{len(schemas)} original SQL answers** with SQLite {summary['sqlite_version']} "
        f"(Python {summary['python_version']}); `PRAGMA foreign_keys=ON`.", '',
        f"**{summary['original_scripts_ok']} succeed; {len(failed_schemas)} fail.** "
        f"A separate scan attempts all {len(statements)} unchanged CREATE statements and finds "
        f"**{len(failed_statements)} failing statements** across those {len(failed_schemas)} examples.", '',
        'Here, an example is one dataset row/schema. Each entry below gives its 1-based JSONL source line, '
        'ID, failing statement/table, and exact SQLite message. SQL line numbers refer to the decoded '
        '`answer` string, not the physical JSONL file.', '',
        'The original whole-script run stops at its first error. The separate statement scan continues '
        'after a failed CREATE, preserving earlier successful tables; later failures are additional '
        'diagnostics that the original run never reaches. Both runs use fresh in-memory databases per '
        'example. No SQL is repaired, no rows are inserted, and successful CREATE statements are not '
        'a proof of valid foreign-key behavior or normalization.', '',
        'Each failed execution reports SQLite\'s first error for that statement. Further defects inside '
        'the same CREATE statement can remain hidden. The failing-statement count does not count every '
        'possible defect in the source.', '',
        'SQLite supplies no error line/column through this Python exception API; the ranges below '
        'identify the complete failing statement. Error messages, including multiline messages, are '
        'preserved without truncation. For malformed apostrophes, the whole-script error can include '
        'SQL following the first failed statement, while the statement-only message ends at its boundary.', '',
        '## Files and reproduction', '',
        '- [schemas.csv](schemas.csv): all examples, including successful ones and the first whole-script error.',
        '- [statements.csv](statements.csv): all CREATE statements, their exact SQL, status and error.',
        '- [errors.jsonl](errors.jsonl): only failures, grouped by example, including original and statement errors.',
        '- [summary.json](summary.json): counts, source checksum and runtime.', '',
        'From the repository root:', '', '```bash',
        'python3 dataset-analysis/RSchema/scripts/inspect_sql_execution.py', '```', '',
        '## Failing examples: first error in the original script', '',
        '| Source line | ID | First failed table | Statement | Exact error (single-line messages) |',
        '|---:|---|---|---:|---|',
    ]
    for record in failed_schemas:
        error = record['original_error']
        display = error if '\n' not in error else '(multiline; full message below)'
        display = display.replace('|', '&#124;').replace('`', '&#96;')
        lines.append(f"| [{record['source_line']}](#example-{record['source_line']}) | `{record['id']}` | "
                     f"`{record['first_failed_table']}` | {record['first_failed_statement']} | `{display}` |")
    lines += ['', '## Exact details for every failing example', '']
    for record in failed_schemas:
        source_line = record['source_line']
        failures = [s for s in failed_statements if s['source_line'] == source_line]
        lines += [f'<a id="example-{source_line}"></a>', '',
                  f"### Example {source_line}: `{record['id']}`", '',
                  f"Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line {source_line}. "
                  f"First failure: statement {record['first_failed_statement']}, table `{record['first_failed_table']}`. "
                  f"SQLite code: `{record['sqlite_errorname']}` ({record['sqlite_errorcode']}).", '',
                  '**Exact original whole-script error:**', '', '```text', record['original_error'], '```', '']
        for statement in failures:
            reached = 'First failure in the original run.' if statement['first_error_in_original'] else 'Additional failure found by continuing; not reached in the original run.'
            lines += [f"**Statement {statement['statement_index']}: `{statement['table']}` "
                      f"(SQL lines {statement['sql_start_line']}-{statement['sql_end_line']}).** {reached}", '',
                      'Exact statement error:', '', '```text', statement['error'], '```', '',
                      'Unmodified failing statement:', '', '```sql', statement['sql'], '```', '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'dataset/RSchema/annotation_ddl.jsonl')
    parser.add_argument('--out-dir', type=Path, default=ANALYSIS_DIR / 'results/sql_execution')
    args = parser.parse_args()
    rows, manifest = load_jsonl(args.input)
    schemas, statements = [], []
    for source_line, row in rows:
        schema, outcomes = inspect_example(source_line, row)
        schemas.append(schema)
        statements.extend(outcomes)
    failed_schemas = [r for r in schemas if r['original_status'] == 'error']
    failed_statements = [r for r in statements if r['status'] == 'error']
    summary = dict(
        source=manifest, python_version=platform.python_version(), sqlite_version=sqlite3.sqlite_version,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        foreign_keys_enabled=True, original_scripts=len(schemas),
        original_scripts_ok=len(schemas) - len(failed_schemas), original_scripts_failed=len(failed_schemas),
        statements_attempted=len(statements), statements_ok=len(statements) - len(failed_statements),
        statements_failed=len(failed_statements),
        schemas_with_multiple_failing_statements=sum(r['failing_statements'] > 1 for r in schemas),
        statement_error_counts=dict(collections.Counter(s['error'] for s in failed_statements)),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / 'schemas.csv', schemas)
    write_csv(args.out_dir / 'statements.csv', statements)
    json_write(args.out_dir / 'summary.json', summary)
    grouped = [dict(schema=r, failed_statements=[s for s in failed_statements if s['source_line'] == r['source_line']]) for r in failed_schemas]
    (args.out_dir / 'errors.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in grouped), encoding='utf-8')
    write_report(args.out_dir / 'errors.md', summary, schemas, statements)
    print(f'Original scripts: {summary["original_scripts_ok"]} succeed, {len(failed_schemas)} fail')
    print(f'Statement scan: {len(statements)} attempted, {len(failed_statements)} fail')
    print(f'Report: {args.out_dir / "errors.md"}')


if __name__ == '__main__':
    main()

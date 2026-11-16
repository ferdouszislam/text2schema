#!/usr/bin/env python3
"""Merge RSchema's DDL-backed examples, repair SQL identifiers, and filter errors.

Only the Python standard library is required. Source files are never modified.
Each example is checked once, then gets at most three repair/re-execution retries.
No-such-column errors are retried unchanged and dropped if they persist.
"""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parents[4]
PREPROCESSING_DIR = Path(__file__).resolve().parents[1]
MAX_RETRIES = 3

# The released DDL has one table header, column, or constraint per physical line.
# Match identifier positions so quoting a table called Table never changes the
# SQL syntax words in CREATE TABLE. Preserve types, clauses, whitespace and order.
TABLE = re.compile(r'^(\s*CREATE\s+TABLE\s+)(.+?)(\s*\(\s*)$', re.I)
PRIMARY_KEY = re.compile(r'^(\s*PRIMARY\s+KEY\s*\()(.*?)(\)\s*,?\s*)$', re.I)
FOREIGN_KEY = re.compile(r'^(\s*FOREIGN\s+KEY\s*\()(.*?)(\)\s+REFERENCES\s+)(.+?)(\s*\()(.*?)(\)\s*,?\s*)$', re.I)
COLUMN = re.compile(r'^(\s*)(.+?)(\s+(?:VARCHAR\s*\(\s*\d+\s*\)|INTEGER|DATETIME|FLOAT|BOOL|BLOB|null)(?=\s|,|$).*)$', re.I)
NEAR_TOKEN = re.compile(r'^near "([^"]+)": syntax error$')


def normalize_identifier(name):
    return name.replace('-', '_').replace('/', '_').replace("'s", '')


def normalize_json_schema(value, changes=None, path=()):
    """Apply only the requested substitutions, preserving lists and duplicates.

    JSON's identifier strings have no embedded SQL quoting. Recursive traversal
    also preserves unusual source FK encodings instead of attempting to fix them.
    """
    if changes is None:
        changes = []
    if isinstance(value, str):
        new = normalize_identifier(value)
        if new != value:
            changes.append(dict(path=list(path), before=value, after=new))
        return new
    if isinstance(value, list):
        return [normalize_json_schema(item, changes, path + (index,)) for index, item in enumerate(value)]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            new_key = normalize_identifier(key)
            if new_key in out:
                raise ValueError(f'Identifier substitutions collide at {path}: {key!r} -> {new_key!r}')
            if new_key != key:
                changes.append(dict(path=list(path) + ['key', key], before=key, after=new_key))
            out[new_key] = normalize_json_schema(item, changes, path + (key,))
        return out
    raise ValueError(f'Unsupported JSON schema value at {path}: {value!r}')


def repair_sql(sql, error):
    """Normalize identifier spelling and quote the currently reported token.

    SQLite's own syntax error drives quoting, so no external keyword list or
    blanket replacement of SQL grammar words is required. A later keyword can
    surface on the next retry. No missing-column correction is attempted.
    """
    if error.lower().startswith('no such column:'):
        return sql, []
    match = NEAR_TOKEN.fullmatch(error)
    quote_token = match[1].casefold() if match else None
    changes = []
    current_line = 0

    def identifier(raw):
        leading = raw[:len(raw) - len(raw.lstrip())]
        trailing = raw[len(raw.rstrip()):]
        name = raw.strip()
        quoted = len(name) >= 2 and name[0] == name[-1] == '"'
        bare = name[1:-1].replace('""', '"') if quoted else name
        new = normalize_identifier(bare)
        if quoted or new.casefold() == quote_token:
            replacement = '"' + new.replace('"', '""') + '"'
        else:
            replacement = new
        if replacement != name:
            changes.append(dict(sql_line=current_line, before=name, after=replacement))
        return leading + replacement + trailing

    def identifier_list(raw):
        # This release has no commas embedded inside an identifier.
        return ','.join(identifier(name) for name in raw.split(','))

    result = []
    for current_line, raw in enumerate(sql.splitlines(keepends=True), 1):
        line = raw.rstrip('\r\n')
        ending = raw[len(line):]
        if not line.strip() or re.fullmatch(r'\s*\);?\s*', line):
            updated = line
        elif match := TABLE.fullmatch(line):
            updated = match[1] + identifier(match[2]) + match[3]
        elif match := PRIMARY_KEY.fullmatch(line):
            updated = match[1] + identifier_list(match[2]) + match[3]
        elif match := FOREIGN_KEY.fullmatch(line):
            updated = match[1] + identifier_list(match[2]) + match[3] + identifier(match[4]) + match[5] + identifier_list(match[6]) + match[7]
        elif match := COLUMN.fullmatch(line):
            updated = match[1] + identifier(match[2]) + match[3]
        else:
            raise ValueError(f'Unsupported DDL layout at SQL line {current_line}: {line}')
        result.append(updated + ending)
    return ''.join(result), changes


def execute_sql(sql):
    """Check a complete answer in a fresh empty SQLite database on every call."""
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            conn.executescript(sql)
        except sqlite3.Error as error:
            return dict(status='error', error=str(error), sqlite_errorcode=getattr(error, 'sqlite_errorcode', None), sqlite_errorname=getattr(error, 'sqlite_errorname', None))
    return dict(status='ok', error='', sqlite_errorcode=None, sqlite_errorname=None)


def preprocess_example(logical, ddl, logical_line, ddl_line):
    if logical['question'] != ddl['question']:
        raise ValueError(f"Question mismatch for ID {ddl['id']}")
    original_sql = ddl['answer']
    sql = original_sql
    attempts = [dict(attempt=0, changes=[], **execute_sql(sql))]
    for retry in range(1, MAX_RETRIES + 1):
        if attempts[-1]['status'] == 'ok':
            break
        sql, changes = repair_sql(sql, attempts[-1]['error'])
        attempts.append(dict(attempt=retry, changes=changes, **execute_sql(sql)))

    kept = attempts[-1]['status'] == 'ok'
    json_changes = []
    json_schema = normalize_json_schema(logical['answer'], json_changes) if kept else logical['answer']
    merged = dict(id=ddl['id'], question=ddl['question'], json_schema=json_schema, ddl_schema=sql,
                  **{key: value for key, value in ddl.items() if key not in {'id', 'question', 'answer'}})
    status = ('kept_repaired' if sql != original_sql else 'kept_original') if kept else 'dropped'
    audit = dict(id=ddl['id'], json_source_line=logical_line, ddl_source_line=ddl_line,
                 status=status, retries=len(attempts) - 1, original_ddl=original_sql,
                 final_ddl=sql, json_identifier_changes=json_changes, attempts=attempts)
    return merged if kept else None, audit, merged if not kept else None


def read_jsonl(path):
    raw = path.read_bytes()
    rows, seen = [], set()

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f'Duplicate object key {key!r} in {path}')
            value[key] = item
        return value

    for line, text in enumerate(raw.decode('utf-8').splitlines(), 1):
        if not text.strip():
            continue
        row = json.loads(text, object_pairs_hook=unique_object)
        if row['id'] in seen:
            raise ValueError(f"Duplicate ID {row['id']} in {path}")
        seen.add(row['id'])
        rows.append((line, row))
    return rows, dict(filename=path.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), records=len(rows))


def json_lines(rows):
    return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)


def write_outputs(out_dir, payloads):
    """Serialize all outputs before calling; stage files before replacement."""
    out_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for name, text in payloads.items():
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=out_dir, prefix='.' + name + '.', delete=False) as stream:
                staged.append((Path(stream.name), out_dir / name))
                stream.write(text)
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def preprocess(data_dir, out_dir):
    logical_rows, logical_source = read_jsonl(data_dir / 'annotation.jsonl')
    ddl_rows, ddl_source = read_jsonl(data_dir / 'annotation_ddl.jsonl')
    logical_index = {row['id']: (line, row) for line, row in logical_rows}
    cleaned, dropped, audits = [], [], []
    for ddl_line, ddl in ddl_rows:
        if ddl['id'] not in logical_index:
            raise ValueError(f"No JSON schema for DDL ID {ddl['id']}")
        logical_line, logical = logical_index[ddl['id']]
        kept, audit, rejected = preprocess_example(logical, ddl, logical_line, ddl_line)
        audits.append(audit)
        if kept is not None:
            cleaned.append(kept)
        else:
            dropped.append(dict(record=rejected, ddl_source_line=ddl_line, final_error=audit['attempts'][-1]['error']))

    ddl_ids = {row['id'] for _, row in ddl_rows}
    summary = dict(
        sources=dict(logical=logical_source, ddl=ddl_source),
        python_version=platform.python_version(), sqlite_version=sqlite3.sqlite_version,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        max_retries=MAX_RETRIES, max_execution_attempts=MAX_RETRIES + 1,
        merged_ddl_rows=len(ddl_rows), excluded_json_only_rows=len(set(logical_index) - ddl_ids),
        kept_rows=len(cleaned), kept_original_sql=sum(a['status'] == 'kept_original' for a in audits),
        kept_repaired_sql=sum(a['status'] == 'kept_repaired' for a in audits), dropped_rows=len(dropped),
        kept_rows_with_json_identifier_changes=sum(a['status'] != 'dropped' and bool(a['json_identifier_changes']) for a in audits),
        dropped=[dict(id=a['id'], ddl_source_line=a['ddl_source_line'], retries=a['retries'], error=a['attempts'][-1]['error']) for a in audits if a['status'] == 'dropped'],
    )
    # Input, processing and serialization errors leave existing outputs intact.
    payloads = {'cleaned.jsonl': json_lines(cleaned), 'dropped.jsonl': json_lines(dropped),
                'audit.jsonl': json_lines(audits), 'summary.json': json.dumps(summary, ensure_ascii=False, indent=2) + '\n'}
    write_outputs(out_dir, payloads)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'dataset/RSchema')
    parser.add_argument('--out-dir', type=Path, default=PREPROCESSING_DIR / 'results')
    args = parser.parse_args()
    summary = preprocess(args.data_dir, args.out_dir)
    print(f"Merged {summary['merged_ddl_rows']} DDL-backed rows; excluded {summary['excluded_json_only_rows']} JSON-only rows")
    print(f"Kept {summary['kept_rows']}: {summary['kept_original_sql']} original SQL, {summary['kept_repaired_sql']} repaired SQL")
    print(f"Dropped {summary['dropped_rows']} rows after {MAX_RETRIES} retries")
    print(f'Cleaned dataset: {args.out_dir / "cleaned.jsonl"}')


if __name__ == '__main__':
    main()

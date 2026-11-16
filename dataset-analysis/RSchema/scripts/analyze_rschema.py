#!/usr/bin/env python3
"""Audit the local RSchema release using Python's standard library only.

The declaration reader is deliberately separate from SQLite execution: invalid SQL
still contributes its explicitly declared tables and columns. It supports the
CREATE TABLE grammar found in this release, and rejects unconsumed statements or
declarations rather than silently producing partial statistics.
"""

import argparse
import collections
import csv
import hashlib
import json
import platform
from pathlib import Path
import re
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_DIR = Path(__file__).resolve().parents[1]
DATASETS = {"logical": "annotation.jsonl", "ddl": "annotation_ddl.jsonl"}
CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^()]+?)\s*\(", re.I)
TYPE = re.compile(r"^(.+?)\s+(VARCHAR\s*\(\s*\d+\s*\)|INTEGER|DATETIME|FLOAT|BOOL|BLOB|null)(?=\s|$)(.*)$", re.I | re.S)
CJK = re.compile(r"[\u3400-\u9fff]")


def normalized(name):
    """Comparison heuristic only; does not modify or repair source labels."""
    return re.sub(r"[\s_]+", "_", unquote(name).strip()).casefold()


def unquote(name):
    name = name.strip()
    if len(name) >= 2 and (name[0], name[-1]) in [('"', '"'), ('`', '`'), ('[', ']'), ("'", "'")]:
        return name[1:-1]
    return name


def scan(text):
    """Yield (offset, character, nesting depth before character), outside quotes.

    SQL line/block comments are skipped. Doubled quote escapes are respected.
    """
    depth = 0
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            end = ']' if quote == '[' else quote
            if c == end:
                if i + 1 < len(text) and text[i + 1] == end:
                    i += 2
                    continue
                quote = None
        elif text.startswith('--', i):
            j = text.find('\n', i)
            i = len(text) if j < 0 else j
            continue
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            if j < 0:
                raise ValueError('Unclosed SQL comment')
            i = j + 2
            continue
        elif c in "\"`['" and not (c == "'" and i > 0 and (text[i - 1].isalnum() or text[i - 1] == '_')):
            quote = c
        else:
            yield i, c, depth
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth < 0:
                    raise ValueError('Unbalanced SQL parentheses')
        i += 1
    if quote or depth:
        raise ValueError('Unclosed SQL quote or parentheses')


def split_sql(text, separator=','):
    cuts = [-1] + [i for i, c, d in scan(text) if c == separator and d == 0] + [len(text)]
    return [text[a + 1:b].strip() for a, b in zip(cuts, cuts[1:]) if text[a + 1:b].strip()]


def names(text):
    return [unquote(x) for x in split_sql(text)]


def parse_ddl(sql):
    tables = []
    for statement in split_sql(sql, ';'):
        match = CREATE.match(statement)
        if not match or not statement.endswith(')'):
            raise ValueError(f'Unsupported statement: {statement[:120]}')
        table = {"name": unquote(match[1]), "columns": [], "primary_keys": [], "foreign_keys": [], "constraints": []}
        body = statement[match.end():-1]
        for declaration in split_sql(body):
            clause = re.sub(r'^CONSTRAINT\s+\S+\s+', '', declaration, flags=re.I)
            pk = re.fullmatch(r'PRIMARY\s+KEY\s*\((.*)\)', clause, re.I | re.S)
            fk = re.fullmatch(r'FOREIGN\s+KEY\s*\((.*?)\)\s+REFERENCES\s+(.+?)\s*\((.*?)\)', clause, re.I | re.S)
            if pk:
                table['primary_keys'].append(names(pk[1]))
            elif fk:
                table['foreign_keys'].append({"columns": names(fk[1]), "target_table": unquote(fk[2]), "target_columns": names(fk[3])})
            elif re.match(r'^(UNIQUE|CHECK)\s*\(', clause, re.I):
                table['constraints'].append(clause)
            else:
                column = TYPE.fullmatch(declaration)
                if not column:
                    raise ValueError(f'Unsupported column declaration: {declaration}')
                name, dtype, tail = column.groups()
                info = {"name": unquote(name), "type": re.sub(r'\s+', '', dtype).upper(), "tail": tail.strip(), "not_null": bool(re.search(r'\bNOT\s+NULL\b', tail, re.I))}
                table['columns'].append(info)
                if re.search(r'\bPRIMARY\s+KEY\b', tail, re.I):
                    table['primary_keys'].append([info['name']])
                inline = re.search(r'\bREFERENCES\s+(.+?)\s*\((.*?)\)', tail, re.I)
                if inline:
                    table['foreign_keys'].append({"columns": [info['name']], "target_table": unquote(inline[1]), "target_columns": names(inline[2])})
                for kind in ('UNIQUE', 'CHECK', 'DEFAULT'):
                    if re.search(rf'\b{kind}\b', tail, re.I):
                        table['constraints'].append(kind)
        tables.append(table)
    return tables


def load_jsonl(path):
    duplicate_keys = []
    current_line = 0

    def object_hook(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                duplicate_keys.append({"line": current_line, "key": key})
            obj[key] = value
        return obj

    raw = path.read_bytes()
    rows = []
    for current_line, line in enumerate(raw.decode('utf-8').splitlines(), 1):
        if line.strip():
            row = json.loads(line, object_pairs_hook=object_hook)
            rows.append((current_line, row))
    ids = [row['id'] for _, row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f'Duplicate IDs in {path}')
    return rows, {"filename": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "records": len(rows), "physical_lines": len(raw.splitlines()), "blank_lines": sum(not line.strip() for line in raw.splitlines()), "duplicate_object_keys": duplicate_keys, "fields": dict(sorted(collections.Counter(k for _, r in rows for k in r).items())), "field_types": {k: dict(collections.Counter(type(r.get(k)).__name__ for _, r in rows)) for k in sorted(set().union(*(r.keys() for _, r in rows)))}}


def describe(values):
    values = sorted(values)
    if not values:
        return {"n": 0}

    def percentile(p):
        pos = (len(values) - 1) * p
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (pos - lo)

    return {"n": len(values), "sum": sum(values), "min": min(values), "p05": percentile(.05), "p25": percentile(.25), "median": statistics.median(values), "mean": statistics.mean(values), "p75": percentile(.75), "p95": percentile(.95), "max": max(values)}


def groups(rows, field, key):
    index = collections.defaultdict(list)
    for line, row in rows:
        index[key(row[field])].append({"line": line, "id": row['id']})
    return [items for items in index.values() if len(items) > 1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sqlite_inventory(sql, tables):
    """Use a fresh in-memory DB for each original answer, with FK checks enabled.

    Successful CREATE is not a proof of valid FKs or normalization. No source
    repairs, inserts, or external databases are used.
    """
    with sqlite3.connect(':memory:') as conn:
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            conn.executescript(sql)
        except sqlite3.Error as error:
            return {"status": "error", "error": str(error)}
        actual = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            quoted = '"' + name.replace('"', '""') + '"'
            actual[name.casefold()] = [r[1].casefold() for r in conn.execute(f'PRAGMA table_info({quoted})')]
        expected = {t['name'].casefold(): [c['name'].casefold() for c in t['columns']] for t in tables}
        if actual != expected:
            raise AssertionError(f'SQLite inventory mismatch: {actual} != {expected}')
        return {"status": "ok", "tables": len(actual), "columns": sum(map(len, actual.values()))}


def audit_references(dataset, line, rid, tables, emit, norm=lambda s: s):
    """Check name resolution; FK target uniqueness is audited separately."""
    lookup = {norm(t['name']): t for t in tables}
    for t in tables:
        columns = [norm(c['name']) for c in t['columns']]
        for col, count in collections.Counter(columns).items():
            if count > 1:
                emit(dataset, line, rid, 'duplicate_column', t['name'], column=col, count=count)
        if not t['primary_keys']:
            emit(dataset, line, rid, 'missing_primary_key', t['name'])
        for pk in t['primary_keys']:
            for col in pk:
                if norm(col) not in columns:
                    emit(dataset, line, rid, 'pk_column_missing', t['name'], column=col)
        for fk in t['foreign_keys']:
            for col in fk['columns']:
                if norm(col) not in columns:
                    emit(dataset, line, rid, 'fk_source_column_missing', t['name'], column=col)
            target = lookup.get(norm(fk['target_table']))
            if target is None:
                emit(dataset, line, rid, 'fk_target_table_missing', t['name'], foreign_key=fk)
                continue
            target_columns = {norm(c['name']) for c in target['columns']}
            for col in fk['target_columns']:
                if norm(col) not in target_columns:
                    emit(dataset, line, rid, 'fk_target_column_missing', t['name'], foreign_key=fk, column=col)
            if len(fk['columns']) != len(fk['target_columns']):
                emit(dataset, line, rid, 'fk_arity_mismatch', t['name'], foreign_key=fk)
            if {norm(c) for c in fk['target_columns']} not in [{norm(c) for c in pk} for pk in target['primary_keys']]:
                emit(dataset, line, rid, 'fk_target_not_entire_declared_pk', t['name'], foreign_key=fk)


def logical_tables(answer, line, rid, emit):
    tables = []
    for name, spec in answer.items():
        expected = {'Attributes', 'Primary key', 'Foreign key'}
        if set(spec) != expected:
            emit('logical', line, rid, 'unexpected_table_fields', name, fields=list(spec))
        attributes = spec['Attributes']
        if not isinstance(attributes, list) or not all(isinstance(c, str) for c in attributes):
            raise ValueError(f'Unexpected attribute structure at logical row {line}')
        primary = spec['Primary key']
        if not isinstance(primary, list) or not all(isinstance(c, str) for c in primary):
            raise ValueError(f'Unexpected primary-key structure at logical row {line}')
        table = {"name": name, "columns": [{"name": c, "type": "", "not_null": False} for c in attributes], "primary_keys": [primary] if primary else [], "foreign_keys": [], "constraints": []}
        for source, targets in spec['Foreign key'].items():
            if not isinstance(targets, dict):
                emit('logical', line, rid, 'malformed_fk_target_map', name, source=source, value=targets)
                continue
            for target, column in targets.items():
                if isinstance(column, list) and all(isinstance(c, str) for c in column):
                    emit('logical', line, rid, 'list_encoded_composite_fk', name, source=source, target=target, value=column)
                    table['foreign_keys'].append({"columns": names(source), "target_table": target, "target_columns": column})
                    continue
                if not isinstance(column, str):
                    emit('logical', line, rid, 'non_string_fk_target_column', name, source=source, target=target, value=column)
                    continue
                table['foreign_keys'].append({"columns": [source], "target_table": target, "target_columns": [column]})
        tables.append(table)
    return tables


def structure(tables, mode):
    """Order-insensitive, multiplicity-preserving signatures for paired audits."""
    out = []
    for t in tables:
        item = [normalized(t['name']), sorted(normalized(c['name']) for c in t['columns'])]
        if mode == 'keys':
            item.extend([sorted(sorted(normalized(c) for c in pk) for pk in t['primary_keys']), sorted((tuple(normalized(c) for c in fk['columns']), normalized(fk['target_table']), tuple(normalized(c) for c in fk['target_columns'])) for fk in t['foreign_keys'])])
        out.append(item)
    return sorted(out)


def write_csv(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def json_write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'dataset/RSchema')
    parser.add_argument('--out-dir', type=Path, default=ANALYSIS_DIR / 'results')
    args = parser.parse_args()
    loaded = {label: load_jsonl(args.data_dir / filename) for label, filename in DATASETS.items()}
    schemas, table_rows, column_rows, issues, comparisons, normalized_findings = [], [], [], [], [], []
    parsed = {}
    domains = collections.Counter()
    subdomains = collections.Counter()

    def emit(dataset, line, rid, kind, table='', **detail):
        issues.append(dict(dataset=dataset, line=line, id=rid, kind=kind, table=table, **detail))

    for dataset, (rows, manifest) in loaded.items():
        parsed[dataset] = {}
        for dup in manifest['duplicate_object_keys']:
            emit(dataset, dup['line'], '', 'duplicate_json_object_key', key=dup['key'])
        for line, row in rows:
            rid, question, answer = row['id'], row['question'], row['answer']
            if dataset == 'logical':
                tables = logical_tables(answer, line, rid, emit)
            else:
                try:
                    tables = parse_ddl(answer)
                except ValueError as error:
                    raise ValueError(f'DDL line {line}, ID {rid}: {error}') from error
                # Independent physical-line pass, using this release's one-item-per-line layout.
                line_tables = []
                for text in answer.splitlines():
                    if re.match(r'^CREATE\s+TABLE\b', text, re.I):
                        line_tables.append([unquote(text[len('CREATE TABLE'):].rsplit('(', 1)[0]), []])
                    elif text.startswith((' ', '\t')) and text.strip() not in ('', ');'):
                        if not re.match(r'^\s*(?:PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE\s*\(|CHECK\s*\(|CONSTRAINT\s)', text, re.I):
                            # Whitespace tokenization is independent of the type-based reader.
                            line_tables[-1][1].append(unquote(text.strip().split()[0]))
                inventory = [[t['name'], [c['name'] for c in t['columns']]] for t in tables]
                if line_tables != inventory:
                    raise AssertionError(f'Independent declaration readers disagree at DDL line {line}')
                result = sqlite_inventory(answer, tables)
                if result['status'] == 'error':
                    emit(dataset, line, rid, 'sqlite_create_error', error=result['error'])
                for table in tables:
                    for c in table['columns']:
                        if c['type'] == 'NULL':
                            emit(dataset, line, rid, 'literal_null_type', table['name'], column=c['name'])
                domain = row['domain']
                if len(domain) != 2 or not all(isinstance(x, str) for x in domain):
                    raise ValueError(f'Unexpected domain format at DDL line {line}: {domain}')
                domains[domain[0]] += 1
                subdomains[tuple(domain)] += 1
            parsed[dataset][rid] = (line, row, tables)
            audit_references(dataset, line, rid, tables, emit)
            normalized_issues = []
            def normalized_emit(dataset, line, rid, kind, table='', **detail):
                finding = dict(dataset=dataset, line=line, id=rid, kind=kind, table=table, **detail)
                normalized_findings.append(finding)
                if kind != 'fk_target_not_entire_declared_pk':
                    normalized_issues.append(finding)
            audit_references(dataset, line, rid, tables, normalized_emit, normalized)
            fk_count = sum(len(t['foreign_keys']) for t in tables)
            answer_text = answer if isinstance(answer, str) else canonical(answer)
            metric = dict(dataset=dataset, line=line, id=rid, question_chars=len(question), question_utf8_bytes=len(question.encode('utf-8')), question_words=len(question.split()), question_lines=len(question.splitlines()), question_has_cjk=bool(CJK.search(question)), question_has_non_ascii=not question.isascii(), answer_chars=len(answer_text), answer_words=len(answer_text.split()), tables=len(tables), columns=sum(len(t['columns']) for t in tables), primary_key_constraints=sum(len(t['primary_keys']) for t in tables), composite_primary_keys=sum(len(pk) > 1 for t in tables for pk in t['primary_keys']), parsed_foreign_keys=fk_count, composite_foreign_keys=sum(len(fk['columns']) > 1 for t in tables for fk in t['foreign_keys']), self_foreign_keys=sum(normalized(fk['target_table']) == normalized(t['name']) for t in tables for fk in t['foreign_keys']), normalized_reference_issue_count=len(normalized_issues), sqlite_status=result['status'] if dataset == 'ddl' else 'not_applicable', domain=row.get('domain', ['', ''])[0], subdomain=row.get('domain', ['', ''])[1])
            schemas.append(metric)
            for t in tables:
                table_rows.append(dict(dataset=dataset, line=line, id=rid, table=t['name'], columns=len(t['columns']), unique_column_names=len({c['name'] for c in t['columns']}), primary_key_constraints=len(t['primary_keys']), primary_key_columns=sum(map(len, t['primary_keys'])), parsed_foreign_keys=len(t['foreign_keys']), explicit_not_null_columns=sum(c['not_null'] for c in t['columns']) if dataset == 'ddl' else '', other_constraints=len(t['constraints']) if dataset == 'ddl' else ''))
                for c in t['columns']:
                    column_rows.append(dict(dataset=dataset, line=line, id=rid, table=t['name'], column=c['name'], declared_type=c['type'], explicit_not_null=c['not_null'] if dataset == 'ddl' else ''))

    logical_ids, ddl_ids = set(parsed['logical']), set(parsed['ddl'])
    for rid in sorted(logical_ids & ddl_ids):
        ll, lr, lt = parsed['logical'][rid]
        dl, dr, dt = parsed['ddl'][rid]
        lnames, dnames = {normalized(t['name']) for t in lt}, {normalized(t['name']) for t in dt}
        lcols = {(normalized(t['name']), normalized(c['name'])) for t in lt for c in t['columns']}
        dcols = {(normalized(t['name']), normalized(c['name'])) for t in dt for c in t['columns']}
        lc = collections.Counter((normalized(t['name']), normalized(c['name'])) for t in lt for c in t['columns'])
        dc = collections.Counter((normalized(t['name']), normalized(c['name'])) for t in dt for c in t['columns'])
        comparisons.append(dict(id=rid, logical_line=ll, ddl_line=dl, question_identical=lr['question'] == dr['question'], tables_identical=lnames == dnames, tables_and_columns_identical=structure(lt, 'columns') == structure(dt, 'columns'), structure_and_keys_identical=structure(lt, 'keys') == structure(dt, 'keys'), logical_only_tables=sorted(lnames - dnames), ddl_only_tables=sorted(dnames - lnames), logical_only_columns=sorted(lcols - dcols), ddl_only_columns=sorted(dcols - lcols), column_multiplicity_differences=[dict(table=t, column=c, logical_count=lc[t,c], ddl_count=dc[t,c]) for t,c in sorted(lc.keys() | dc.keys()) if lc[t,c] != dc[t,c]]))

    summary = {"method_version": 1, "files": {d: meta for d, (_, meta) in loaded.items()}, "datasets": {}, "alignment": {"shared_ids": len(logical_ids & ddl_ids), "logical_only_ids": sorted(logical_ids - ddl_ids), "ddl_only_ids": sorted(ddl_ids - logical_ids), "ddl_preserves_logical_subset_order": list(parsed['ddl']) == [rid for rid in parsed['logical'] if rid in ddl_ids], "shared_logical_column_entries": sum(len(t['columns']) for rid in ddl_ids for t in parsed['logical'][rid][2]), "logical_only_tables": sum(len(parsed['logical'][rid][2]) for rid in logical_ids - ddl_ids), "logical_only_column_entries": sum(len(t['columns']) for rid in logical_ids - ddl_ids for t in parsed['logical'][rid][2]), **{k: sum(p[k] for p in comparisons) for k in ['question_identical', 'tables_identical', 'tables_and_columns_identical', 'structure_and_keys_identical']}}, "domain_counts": dict(domains.most_common()), "subdomain_pair_count": len(subdomains)}
    histogram = []
    for dataset, (rows, _) in loaded.items():
        selected = [r for r in schemas if r['dataset'] == dataset]
        selected_tables = [r for r in table_rows if r['dataset'] == dataset]
        selected_columns = [r for r in column_rows if r['dataset'] == dataset]
        selected_issues = [r for r in issues if r['dataset'] == dataset]
        stats = {k: describe([r[k] for r in selected]) for k in ['question_chars', 'question_utf8_bytes', 'question_words', 'question_lines', 'answer_chars', 'answer_words', 'tables', 'columns', 'primary_key_constraints', 'composite_primary_keys', 'parsed_foreign_keys', 'composite_foreign_keys', 'self_foreign_keys']}
        stats['columns_per_table'] = describe([r['columns'] for r in selected_tables])
        stats['unique_column_names_within_tables_total'] = sum(r['unique_column_names'] for r in selected_tables)
        stats['type_counts'] = dict(collections.Counter(c['declared_type'] for c in selected_columns))
        stats['issues'] = {kind: {"occurrences": sum(r['kind'] == kind for r in selected_issues), "schemas": len({r['line'] for r in selected_issues if r['kind'] == kind})} for kind in sorted({r['kind'] for r in selected_issues})}
        stats['schemas_with_normalized_reference_issues'] = sum(r['normalized_reference_issue_count'] > 0 for r in selected)
        reference_kinds = {'duplicate_column', 'missing_primary_key', 'pk_column_missing', 'fk_source_column_missing', 'fk_target_table_missing', 'fk_target_column_missing', 'fk_arity_mismatch'}
        stats['schemas_with_exact_reference_issues'] = len({r['line'] for r in selected_issues if r['kind'] in reference_kinds})
        stats['normalized_reference_issues'] = {kind: {"occurrences": sum(r['kind'] == kind for r in normalized_findings if r['dataset'] == dataset), "schemas": len({r['line'] for r in normalized_findings if r['dataset'] == dataset and r['kind'] == kind})} for kind in sorted({r['kind'] for r in normalized_findings if r['dataset'] == dataset})}
        stats['table_name_non_ascii_count'] = sum(not t['table'].isascii() for t in selected_tables)
        stats['column_name_non_ascii_count'] = sum(not c['column'].isascii() for c in selected_columns)
        if dataset == 'logical':
            stats['raw_fk_source_entries'] = sum(len(spec['Foreign key']) for _, r in rows for spec in r['answer'].values())
            stats['raw_fk_target_entries'] = sum(len(targets) for _, r in rows for spec in r['answer'].values() for targets in spec['Foreign key'].values())
        stats['question_cjk_records'] = sum(r['question_has_cjk'] for r in selected)
        stats['question_non_ascii_records'] = sum(r['question_has_non_ascii'] for r in selected)
        stats['explicit_not_null_columns'] = sum(c['explicit_not_null'] for c in selected_columns) if dataset == 'ddl' else None
        stats['other_constraint_declarations'] = sum(t['other_constraints'] for t in selected_tables) if dataset == 'ddl' else None
        stats['schemas_with_composite_primary_keys'] = sum(r['composite_primary_keys'] > 0 for r in selected)
        stats['schemas_with_zero_parsed_foreign_keys'] = sum(r['parsed_foreign_keys'] == 0 for r in selected)
        stats['blank_required_fields'] = {field: sum(not r[field] for _, r in rows) for field in ['id', 'question', 'answer']}
        stats['duplicate_questions_exact'] = groups(rows, 'question', str)
        stats['duplicate_questions_casefold_whitespace'] = groups(rows, 'question', lambda q: ' '.join(q.split()).casefold())
        stats['duplicate_answers_exact'] = groups(rows, 'answer', canonical)
        stats['extrema'] = {k: {edge: [dict(line=r['line'], id=r['id'], value=r[k]) for r in selected if r[k] == stats[k][edge]] for edge in ['min', 'max']} for k in ['question_words', 'question_chars', 'tables', 'columns']}
        stats['columns_per_table_extrema'] = {edge: [r for r in selected_tables if r['columns'] == stats['columns_per_table'][edge]] for edge in ['min', 'max']}
        if dataset == 'ddl':
            stats['independent_line_inventory_matches'] = len(rows)
            stats['sqlite_create_ok'] = sum(r['sqlite_status'] == 'ok' for r in selected)
            stats['sqlite_error_counts'] = dict(collections.Counter(r['error'] for r in selected_issues if r['kind'] == 'sqlite_create_error'))
            stats['metadata'] = {k: {"nonempty": sum(bool(r[k]) for _, r in rows), "unique": len({r[k] for _, r in rows}), "cjk_records": sum(bool(CJK.search(r[k])) for _, r in rows)} for k in ['remarks', 'assign_to', 'assign_to_round2']}
            stats['table_name_cjk_count'] = sum(bool(CJK.search(t['table'])) for t in selected_tables)
            stats['column_name_cjk_count'] = sum(bool(CJK.search(c['column'])) for c in selected_columns)
        summary['datasets'][dataset] = stats
        for metric in ['tables', 'columns', 'question_words']:
            for value, count in sorted(collections.Counter(r[metric] for r in selected).items()):
                histogram.append(dict(dataset=dataset, metric=metric, value=value, count=count))
        for value, count in sorted(collections.Counter(r['columns'] for r in selected_tables).items()):
            histogram.append(dict(dataset=dataset, metric='columns_per_table', value=value, count=count))

    # All source data is processed before replacing output files.
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_write(args.out_dir / 'summary.json', summary)
    json_write(args.out_dir / 'environment.json', dict(python_version=platform.python_version(), sqlite_version=sqlite3.sqlite_version, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    write_csv(args.out_dir / 'schema_metrics.csv', schemas)
    write_csv(args.out_dir / 'table_metrics.csv', table_rows)
    write_csv(args.out_dir / 'column_metrics.csv', column_rows)
    write_csv(args.out_dir / 'histograms.csv', histogram)
    write_csv(args.out_dir / 'domains.csv', [dict(domain=major, subdomain=minor, schemas=count) for (major, minor), count in sorted(subdomains.items())])
    examples = []
    selected_lines = {'logical': [1, 154, 319, 406, 487], 'ddl': [1, 5, 57, 58, 59, 80, 81, 82, 123, 228, 252, 260, 313, 342, 349]}
    for dataset, wanted in selected_lines.items():
        for line, row in loaded[dataset][0]:
            if line in wanted:
                examples.append(dict(dataset=dataset, line=line, record=row))
    json_write(args.out_dir / 'examples.json', examples)
    for filename, records in [('issues.jsonl', issues), ('normalized_issues.jsonl', normalized_findings), ('paired_comparison.jsonl', comparisons)]:
        (args.out_dir / filename).write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in records), encoding='utf-8')
    write_statistics(args.out_dir / 'statistics.md', summary)
    print(f'Wrote analysis to {args.out_dir}')
    for dataset, info in summary['datasets'].items():
        print(f"{dataset}: {summary['files'][dataset]['records']} schemas, {info['tables']['sum']} tables, {info['columns']['sum']} columns")
    print(f"DDL: {summary['datasets']['ddl']['sqlite_create_ok']} SQLite CREATE successes; all {len(parsed['ddl'])} declaration inventories independently cross-checked")


def write_statistics(path, summary):
    lines = ['# Generated RSchema statistics', '', 'Regenerate with `python3 dataset-analysis/RSchema/scripts/analyze_rschema.py`. See `../README.md` for definitions and `../report.md` for interpretation.', '', 'Values below use linear interpolation for percentiles and whitespace splitting for words. Means/percentiles are rounded here to two decimals; JSON retains the computed values.', '']
    for dataset, stats in summary['datasets'].items():
        lines += [f'## {dataset}: {summary["files"][dataset]["filename"]}', '', '| Metric | Total | Min | P25 | Median | Mean | P75 | P95 | Max |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for key in ['question_words', 'question_chars', 'question_utf8_bytes', 'question_lines', 'answer_chars', 'tables', 'columns', 'columns_per_table', 'primary_key_constraints', 'composite_primary_keys', 'parsed_foreign_keys', 'composite_foreign_keys', 'self_foreign_keys']:
            s = stats[key]
            lines.append('| ' + key + ' | ' + ' | '.join(f'{s[k]:,.2f}'.removesuffix('.00') for k in ['sum', 'min', 'p25', 'median', 'mean', 'p75', 'p95', 'max']) + ' |')
        lines += ['', '### Detected issues (categories overlap)', '', '| Kind | Occurrences | Schemas |', '|---|---:|---:|']
        lines += [f'| {kind} | {n["occurrences"]} | {n["schemas"]} |' for kind, n in stats['issues'].items()]
        lines += ['']
    lines += ['## Paired records', '', '| Check | Count |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in summary['alignment'].items() if type(v) is int]
    lines += ['', '## SQL declared types', '', '| Type | Columns |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in summary['datasets']['ddl']['type_counts'].items()]
    lines += ['', '## Major domains (DDL only)', '', '| Source label | Schemas |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in summary['domain_counts'].items()]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

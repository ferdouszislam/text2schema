#!/usr/bin/env python3
"""Independently check the audited RSchema snapshot and repeat its extraction.

This is intentionally a release-specific check, not a general SQL parser test.
It uses raw JSON lists and physical SQL declaration lines rather than importing
the analyzer's declaration reader. A changed input snapshot must be re-audited.
"""

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
ANALYSIS_DIR = Path(__file__).resolve().parents[1]
EXPECTED = {
    'logical': ('annotation.jsonl', '3ab18c248076f2df7ed4f82b3f8e4dc670b6973a1ce5d65caf3930aed9b7c4e4', 518, 2436, 11708),
    'ddl': ('annotation_ddl.jsonl', 'ce17d9aac0acba21b6d91aff9af1d3663ce1598176dea391b04dbfcb16a4f2e6', 381, 1748, 8453),
}


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'dataset/RSchema')
    parser.add_argument('--results-dir', type=Path, default=ANALYSIS_DIR / 'results')
    args = parser.parse_args()
    summary = json.loads((args.results_dir / 'summary.json').read_text())
    with (args.results_dir / 'table_metrics.csv').open(newline='') as stream:
        exported_tables = list(csv.DictReader(stream))
    with (args.results_dir / 'schema_metrics.csv').open(newline='') as stream:
        exported_schemas = list(csv.DictReader(stream))
    for dataset, (filename, digest, n_schemas, n_tables, n_columns) in EXPECTED.items():
        raw = (args.data_dir / filename).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, f'{filename}: snapshot differs from the audited release')
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        inventory = []
        for row in rows:
            if dataset == 'logical':
                inventory += [(row['id'], table, len(spec['Attributes'])) for table, spec in row['answer'].items()]
            else:
                # This snapshot has one table header or column/constraint per line.
                current = None
                count = 0
                for line in row['answer'].splitlines():
                    if line.startswith('CREATE TABLE '):
                        if current is not None:
                            inventory.append((row['id'], current, count))
                        current, count = line[len('CREATE TABLE '):].split('(', 1)[0].strip(), 0
                    elif line[:1].isspace() and not re.match(r'^\s*(?:PRIMARY\s+KEY|FOREIGN\s+KEY)\s*\(', line):
                        count += 1
                if current is not None:
                    inventory.append((row['id'], current, count))
        require((len(rows), len(inventory), sum(n for _, _, n in inventory)) == (n_schemas, n_tables, n_columns), f'{dataset}: independent totals disagree')
        exported = [(r['id'], r['table'], int(r['columns'])) for r in exported_tables if r['dataset'] == dataset]
        require(collections.Counter(inventory) == collections.Counter(exported), f'{dataset}: per-table CSV differs from independent inventory')
        question_lookup = {r['id']: (len(r['question']), len(r['question'].split())) for r in rows}
        metrics = {r['id']: (int(r['question_chars']), int(r['question_words'])) for r in exported_schemas if r['dataset'] == dataset}
        require(question_lookup == metrics, f'{dataset}: question lengths disagree')
        require(summary['files'][dataset]['sha256'] == digest, f'{dataset}: stale manifest')
        print(f'PASS {dataset}: independently checked {n_schemas} schemas, {n_tables} tables, {n_columns} columns and every question length')

    # Re-run to check that the checked-in extraction is current and deterministic.
    with tempfile.TemporaryDirectory(prefix='rschema-verification-') as temp:
        subprocess.run([sys.executable, str(ANALYSIS_DIR / 'scripts/analyze_rschema.py'), '--data-dir', str(args.data_dir.resolve()), '--out-dir', temp], check=True, stdout=subprocess.DEVNULL)
        actual_names = {p.name for p in args.results_dir.iterdir() if p.is_file()}
        fresh_names = {p.name for p in Path(temp).iterdir() if p.is_file()}
        require(actual_names == fresh_names, 'generated file inventory differs')
        for name in sorted(fresh_names):
            require((args.results_dir / name).read_bytes() == (Path(temp) / name).read_bytes(), f'{name}: stale output or different runtime; regenerate using this Python/SQLite runtime')
        print(f'PASS all {len(fresh_names)} generated files match a fresh run byte for byte')


if __name__ == '__main__':
    main()

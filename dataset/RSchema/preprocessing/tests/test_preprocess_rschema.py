"""Behavioral checks for the requested merge, repairs, retries and filtering.

Run from the repository root:
    python3 -m unittest discover -s dataset/RSchema/preprocessing/tests -v
"""

import copy
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/preprocess_rschema.py'
SPEC = importlib.util.spec_from_file_location('preprocess_rschema', SCRIPT)
preprocessor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preprocessor)


def logical_record(rid, answer=None):
    if answer is None:
        answer = {'Item': {'Attributes': ['id'], 'Primary key': ['id'], 'Foreign key': {}}}
    return {'id': rid, 'question': f'Keep the original specification for {rid}.', 'answer': answer}


def ddl_record(rid, sql=None):
    if sql is None:
        sql = 'CREATE TABLE Item (\n    id INTEGER PRIMARY KEY\n);'
    return {
        'id': rid,
        'question': logical_record(rid)['question'],
        'answer': sql,
        'remarks': 'Original annotation, unchanged.',
        'assign_to': 'annotator',
        'assign_to_round2': 'reviewer',
        'domain': ['原始领域', '原始子领域'],
    }


def write_sources(data_dir, logical, ddl):
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename, records in [('annotation.jsonl', logical), ('annotation_ddl.jsonl', ddl)]:
        (data_dir / filename).write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8'
        )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}


class PreprocessBehaviorTests(unittest.TestCase):
    def test_merge_joins_by_id_preserves_ddl_order_question_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            data, out = Path(temp) / 'data', Path(temp) / 'out'
            write_sources(data, [logical_record('a'), logical_record('json-only'), logical_record('b')],
                          [ddl_record('b'), ddl_record('a')])
            before = snapshot(data)
            summary = preprocessor.preprocess(data, out)
            kept = read_jsonl(out / 'cleaned.jsonl')
            self.assertEqual([row['id'] for row in kept], ['b', 'a'])
            self.assertEqual(summary['excluded_json_only_rows'], 1)
            for row in kept:
                original = ddl_record(row['id'])
                self.assertEqual(row['question'], original['question'])
                self.assertEqual(row['json_schema'], logical_record(row['id'])['answer'])
                self.assertEqual(row['ddl_schema'], original['answer'])
                for field in ['remarks', 'assign_to', 'assign_to_round2', 'domain']:
                    self.assertEqual(row[field], original[field])
            self.assertEqual(snapshot(data), before)

    def test_symbols_possessives_and_keyword_quoting_cover_identifier_positions(self):
        schema = {
            'Table': {
                'Attributes': ["owner's-id", 'path/value', 'Group', 'Group'],
                'Primary key': ["owner's-id"],
                'Foreign key': {"owner's-id": {'Table': "owner's-id"}},
            }
        }
        logical = logical_record('names', schema)
        sql = """CREATE TABLE Table (
    owner's-id INTEGER PRIMARY KEY,
    path/value VARCHAR(255),
    Group INTEGER,
    FOREIGN KEY (owner's-id) REFERENCES Table(owner's-id)
);"""
        ddl = ddl_record('names', sql)
        original_logical, original_ddl = copy.deepcopy(logical), copy.deepcopy(ddl)
        kept, audit, dropped = preprocessor.preprocess_example(logical, ddl, 4, 2)
        self.assertIsNone(dropped)
        self.assertEqual(audit['retries'], 2)
        self.assertIn('CREATE TABLE "Table" (', kept['ddl_schema'])
        self.assertNotIn('CREATE "TABLE"', kept['ddl_schema'])
        self.assertIn('owner_id INTEGER PRIMARY KEY', kept['ddl_schema'])
        self.assertIn('path_value VARCHAR(255)', kept['ddl_schema'])
        self.assertIn('"Group" INTEGER', kept['ddl_schema'])
        self.assertIn('FOREIGN KEY (owner_id) REFERENCES "Table"(owner_id)', kept['ddl_schema'])
        self.assertEqual(kept['json_schema']['Table']['Attributes'], ['owner_id', 'path_value', 'Group', 'Group'])
        self.assertEqual(kept['json_schema']['Table']['Primary key'], ['owner_id'])
        self.assertEqual(kept['json_schema']['Table']['Foreign key'], {'owner_id': {'Table': 'owner_id'}})
        self.assertEqual(logical, original_logical)
        self.assertEqual(ddl, original_ddl)
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.executescript(kept['ddl_schema'])

    def test_each_retry_starts_with_a_fresh_database(self):
        sql = """CREATE TABLE Customer (
    id INTEGER PRIMARY KEY
);

CREATE TABLE Order (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    FOREIGN KEY (customer_id) REFERENCES Customer(id)
);"""
        kept, audit, dropped = preprocessor.preprocess_example(
            logical_record('fresh'), ddl_record('fresh', sql), 1, 1)
        self.assertIsNotNone(kept)
        self.assertIsNone(dropped)
        self.assertEqual(audit['retries'], 1)
        self.assertEqual([a['status'] for a in audit['attempts']], ['error', 'ok'])
        self.assertIn('CREATE TABLE "Order"', kept['ddl_schema'])

    def test_missing_column_is_unchanged_and_dropped_after_three_retries(self):
        sql = """CREATE TABLE Item (
    id INTEGER,
    PRIMARY KEY (missing)
);"""
        kept, audit, dropped = preprocessor.preprocess_example(
            logical_record('missing'), ddl_record('missing', sql), 6, 3)
        self.assertIsNone(kept)
        self.assertEqual(audit['status'], 'dropped')
        self.assertEqual(audit['retries'], 3)
        self.assertEqual([a['attempt'] for a in audit['attempts']], [0, 1, 2, 3])
        self.assertEqual([a['error'] for a in audit['attempts']], ['no such column: missing'] * 4)
        self.assertTrue(all(a['changes'] == [] for a in audit['attempts']))
        self.assertEqual(audit['original_ddl'], sql)
        self.assertEqual(audit['final_ddl'], sql)
        self.assertEqual(dropped['ddl_schema'], sql)

    def test_unresolved_keyword_error_drops_at_three_retry_limit(self):
        sql = '\n\n'.join(
            f'CREATE TABLE {name} (\n    id INTEGER PRIMARY KEY\n);'
            for name in ['Table', 'Order', 'Transaction', 'Group']
        )
        kept, audit, dropped = preprocessor.preprocess_example(
            logical_record('limit'), ddl_record('limit', sql), 1, 1)
        self.assertIsNone(kept)
        self.assertIsNotNone(dropped)
        self.assertEqual(audit['retries'], 3)
        self.assertEqual(len(audit['attempts']), 4)
        self.assertEqual(audit['attempts'][-1]['error'], 'near "Group": syntax error')

    def test_invalid_input_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            data, out = Path(temp) / 'data', Path(temp) / 'out'
            write_sources(data, [logical_record('a')], [ddl_record('a')])
            preprocessor.preprocess(data, out)
            before = snapshot(out)
            (data / 'annotation_ddl.jsonl').write_text('{broken json\n', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                preprocessor.preprocess(data, out)
            self.assertEqual(snapshot(out), before)

    def test_serialization_failure_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            data, out = Path(temp) / 'data', Path(temp) / 'out'
            write_sources(data, [logical_record('a')], [ddl_record('a')])
            preprocessor.preprocess(data, out)
            before = snapshot(out)
            with patch.object(preprocessor.json, 'dumps', side_effect=TypeError('deliberate serialization failure')):
                with self.assertRaisesRegex(TypeError, 'deliberate serialization failure'):
                    preprocessor.preprocess(data, out)
            self.assertEqual(snapshot(out), before)

    def test_full_snapshot_results_execute_and_reproduce_without_source_changes(self):
        data = ROOT / 'dataset/RSchema'
        source_paths = [data / 'annotation.jsonl', data / 'annotation_ddl.jsonl']
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            summary = preprocessor.preprocess(data, out)
            self.assertEqual(summary['merged_ddl_rows'], 381)
            self.assertEqual(summary['excluded_json_only_rows'], 137)
            self.assertEqual(summary['kept_rows'], 375)
            self.assertEqual(summary['kept_original_sql'], 315)
            self.assertEqual(summary['kept_repaired_sql'], 60)
            self.assertEqual(summary['dropped_rows'], 6)
            dropped = read_jsonl(out / 'dropped.jsonl')
            self.assertEqual([r['ddl_source_line'] for r in dropped], [5, 35, 74, 83, 137, 175])
            self.assertTrue(all(r['final_error'].startswith('no such column:') for r in dropped))
            audits = read_jsonl(out / 'audit.jsonl')
            self.assertTrue(all(a['retries'] == 3 for a in audits if a['status'] == 'dropped'))
            for row in read_jsonl(out / 'cleaned.jsonl'):
                with closing(sqlite3.connect(':memory:')) as conn:
                    conn.execute('PRAGMA foreign_keys=ON')
                    conn.executescript(row['ddl_schema'])
            first_run = snapshot(out)
            preprocessor.preprocess(data, out)
            self.assertEqual(snapshot(out), first_run)
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}, before)


if __name__ == '__main__':
    unittest.main()

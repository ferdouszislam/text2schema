# Generated RSchema statistics

Regenerate with `python3 dataset/RSchema/analysis/scripts/analyze_rschema.py`. See `../README.md` for definitions and `../report.md` for interpretation.

Values below use linear interpolation for percentiles and whitespace splitting for words. Means/percentiles are rounded here to two decimals; JSON retains the computed values.

## logical: annotation.jsonl

| Metric | Total | Min | P25 | Median | Mean | P75 | P95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| question_words | 71,792 | 37 | 89 | 122.50 | 138.59 | 164 | 302 | 476 |
| question_chars | 509,487 | 261 | 614.50 | 868.50 | 983.57 | 1,163.50 | 2,091.50 | 3,577 |
| question_utf8_bytes | 509,594 | 261 | 614.50 | 868.50 | 983.77 | 1,163.50 | 2,091.50 | 3,577 |
| question_lines | 2,460 | 1 | 1 | 1 | 4.75 | 7 | 17.15 | 31 |
| answer_chars | 463,220 | 270 | 591.25 | 831.50 | 894.25 | 1,087.25 | 1,587.65 | 3,125 |
| tables | 2,436 | 1 | 3 | 4 | 4.70 | 6 | 8 | 18 |
| columns | 11,708 | 5 | 15 | 21 | 22.60 | 27 | 41 | 71 |
| columns_per_table | 11,708 | 1 | 3 | 4 | 4.81 | 6 | 9 | 18 |
| primary_key_constraints | 2,436 | 1 | 3 | 4 | 4.70 | 6 | 8 | 18 |
| composite_primary_keys | 638 | 0 | 0 | 1 | 1.23 | 2 | 3 | 6 |
| parsed_foreign_keys | 2,146 | 0 | 2 | 4 | 4.14 | 6 | 9 | 18 |
| composite_foreign_keys | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| self_foreign_keys | 29 | 0 | 0 | 0 | 0.06 | 0 | 0 | 3 |

### Detected issues (categories overlap)

| Kind | Occurrences | Schemas |
|---|---:|---:|
| duplicate_column | 3 | 3 |
| fk_source_column_missing | 41 | 32 |
| fk_target_column_missing | 51 | 29 |
| fk_target_not_entire_declared_pk | 73 | 39 |
| fk_target_table_missing | 34 | 16 |
| list_encoded_composite_fk | 2 | 1 |
| non_string_fk_target_column | 2 | 1 |
| pk_column_missing | 39 | 26 |

## ddl: annotation_ddl.jsonl

| Metric | Total | Min | P25 | Median | Mean | P75 | P95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| question_words | 52,619 | 37 | 87 | 120 | 138.11 | 165 | 308 | 440 |
| question_chars | 372,972 | 261 | 609 | 848 | 978.93 | 1,162 | 2,125 | 3,228 |
| question_utf8_bytes | 373,061 | 261 | 609 | 848 | 979.16 | 1,162 | 2,125 | 3,232 |
| question_lines | 1,815 | 1 | 1 | 1 | 4.76 | 7 | 17 | 31 |
| answer_chars | 432,143 | 300 | 748 | 1,044 | 1,134.23 | 1,436 | 2,051 | 3,136 |
| tables | 1,748 | 2 | 3 | 4 | 4.59 | 5 | 8 | 11 |
| columns | 8,453 | 5 | 15 | 21 | 22.19 | 27 | 39 | 63 |
| columns_per_table | 8,453 | 1 | 3 | 5 | 4.84 | 6 | 9 | 18 |
| primary_key_constraints | 1,746 | 2 | 3 | 4 | 4.58 | 5 | 8 | 11 |
| composite_primary_keys | 451 | 0 | 0 | 1 | 1.18 | 2 | 3 | 5 |
| parsed_foreign_keys | 1,496 | 0 | 2 | 3 | 3.93 | 5 | 8 | 15 |
| composite_foreign_keys | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| self_foreign_keys | 17 | 0 | 0 | 0 | 0.04 | 0 | 0 | 3 |

### Detected issues (categories overlap)

| Kind | Occurrences | Schemas |
|---|---:|---:|
| fk_target_not_entire_declared_pk | 7 | 4 |
| literal_null_type | 10 | 2 |
| missing_primary_key | 2 | 2 |
| pk_column_missing | 7 | 6 |
| sqlite_create_error | 66 | 66 |

## Paired records

| Check | Count |
|---|---:|
| shared_ids | 381 |
| shared_logical_column_entries | 8456 |
| logical_only_tables | 688 |
| logical_only_column_entries | 3252 |
| question_identical | 381 |
| tables_identical | 381 |
| tables_and_columns_identical | 378 |
| structure_and_keys_identical | 376 |

## SQL declared types

| Type | Columns |
|---|---:|
| INTEGER | 3191 |
| VARCHAR(255) | 3598 |
| DATETIME | 1062 |
| FLOAT | 494 |
| BOOL | 69 |
| BLOB | 29 |
| NULL | 10 |

## Major domains (DDL only)

| Source label | Schemas |
|---|---:|
| 信息传输、软件和信息技术服务业 | 70 |
| 文化、体育和娱乐业 | 43 |
| 教育 | 38 |
| 批发和零售业 | 37 |
| 租赁和商务服务业 | 33 |
| 金融业 | 20 |
| 居民服务、修理和其他服务业 | 19 |
| 住宿和餐饮业 | 17 |
| 交通运输、仓储和邮政业 | 15 |
| 卫生和社会工作 | 15 |
| 农、林、牧、渔业 | 13 |
| 科学研究和技术服务业 | 11 |
| 水利、环境和公共设施管理业 | 10 |
| 公共管理、社会保障和社会组织 | 10 |
| 生活生产和供应业 | 8 |
| 制造业 | 7 |
| 建筑业 | 7 |
| 房地产业 | 5 |
| 采矿业 | 3 |

#!/usr/bin/env python3
"""Plot table, column, and specification-word counts from cleaned RSchema rows.

Counts come from executing retained DDL, not duplicate-prone JSON attribute
lists. Run with the repository's .venv after installing root requirements.txt.
"""

import argparse
from contextlib import closing
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import tempfile

PREPROCESSING_DIR = Path(__file__).resolve().parents[1]
METRICS = {
    'tables': 'Tables per database',
    'columns': 'Columns per database',
    'specification_words': 'Specification words',
}


def extract_metrics(path):
    raw = path.read_bytes()
    rows = []
    ids = set()
    for line, text in enumerate(raw.decode('utf-8').splitlines(), 1):
        if not text.strip():
            continue
        record = json.loads(text)
        if record['id'] in ids:
            raise ValueError(f"Duplicate ID at input line {line}: {record['id']}")
        ids.add(record['id'])
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            try:
                conn.executescript(record['ddl_schema'])
            except sqlite3.Error as error:
                raise ValueError(f"Input line {line}, ID {record['id']}: {error}") from error
            tables = [name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name") if not name.startswith('sqlite_')]
            columns = 0
            for name in tables:
                quoted = '"' + name.replace('"', '""') + '"'
                columns += len(conn.execute(f'PRAGMA table_info({quoted})').fetchall())
        rows.append(dict(id=record['id'], tables=len(tables), columns=columns,
                         specification_words=len(record['question'].split())))
    if not rows:
        raise ValueError('No examples in the preprocessed dataset')
    return rows, hashlib.sha256(raw).hexdigest()


def box_statistics(values):
    values = sorted(values)

    def percentile(p):
        position = (len(values) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)

    q1, median, q3 = (percentile(p) for p in (.25, .5, .75))
    iqr = q3 - q1
    lower_fence, upper_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = [v for v in values if lower_fence <= v <= upper_fence]
    outliers = [v for v in values if v < lower_fence or v > upper_fence]
    return dict(n=len(values), total=sum(values), minimum=values[0], q1=q1,
                median=median, mean=statistics.mean(values), q3=q3, maximum=values[-1],
                iqr=iqr, lower_fence=lower_fence, upper_fence=upper_fence,
                lower_whisker=min(inside), upper_whisker=max(inside),
                outlier_count=len(outliers), outliers=outliers)


def render_plots(rows, stats, out_dir):
    # Headless rendering, with the font cache in a writable temporary directory.
    # Keep an explicit user-provided MPLCONFIGDIR if one is configured.
    with tempfile.TemporaryDirectory(prefix='rschema-matplotlib-') as config_dir:
        previous_config = os.environ.get('MPLCONFIGDIR')
        os.environ.setdefault('MPLCONFIGDIR', config_dir)
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.ticker import MaxNLocator

            style = {'font.family': 'DejaVu Sans', 'font.size': 11,
                     'axes.titleweight': 'bold', 'axes.edgecolor': '#cbd5e1',
                     'axes.labelcolor': '#334155', 'xtick.color': '#475569',
                     'ytick.color': '#475569', 'svg.hashsalt': 'rschema-preprocessed-counts'}
            with plt.rc_context(style):
                fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.7))
                fig.suptitle('RSchema after preprocessing', fontsize=18, fontweight='bold', y=.97)
                fig.text(.5, .895, f'{len(rows)} retained database specifications', ha='center', color='#475569')
                colors = ['#2563eb', '#0f766e', '#b45309']
                for ax, (key, title), color in zip(axes, METRICS.items(), colors):
                    s = stats[key]
                    ax.bxp([dict(q1=s['q1'], med=s['median'], q3=s['q3'],
                                 whislo=s['lower_whisker'], whishi=s['upper_whisker'],
                                 fliers=s['outliers'])], widths=.34, orientation='vertical',
                           patch_artist=True, boxprops=dict(facecolor=color, alpha=.22, edgecolor=color, linewidth=1.8),
                           medianprops=dict(color=color, linewidth=2.4),
                           whiskerprops=dict(color=color, linewidth=1.5),
                           capprops=dict(color=color, linewidth=1.5),
                           flierprops=dict(marker='o', markersize=4, markerfacecolor='none', markeredgecolor=color, alpha=.8))
                    ax.set_title(title, fontsize=12, pad=12)
                    ax.set_xticks([])
                    ax.set_xlim(.5, 1.5)
                    ax.set_ylim(bottom=0, top=max(s['maximum'] * 1.1, 1))
                    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
                    ax.set_axisbelow(True)
                    ax.grid(axis='y', color='#e2e8f0', linewidth=.7)
                    ax.spines[['top', 'right', 'bottom']].set_visible(False)
                    ax.set_xlabel(f"Median {s['median']:g}  |  Q1-Q3 {s['q1']:g}-{s['q3']:g}", labelpad=12, fontsize=10)
                fig.text(.5, .035, 'Boxes: Q1-Q3  |  Center lines: medians  |  Whiskers: 1.5 x IQR  |  Circles: outliers',
                         ha='center', fontsize=9, color='#475569')
                fig.subplots_adjust(left=.065, right=.98, top=.76, bottom=.19, wspace=.34)
                try:
                    fig.savefig(out_dir / 'counts_boxplots.png', dpi=220, facecolor='white')
                    fig.savefig(out_dir / 'counts_boxplots.svg', facecolor='white', metadata={'Date': None})
                finally:
                    plt.close(fig)
            return matplotlib.__version__
        finally:
            if previous_config is None:
                os.environ.pop('MPLCONFIGDIR', None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=PREPROCESSING_DIR / 'results/cleaned.jsonl')
    parser.add_argument('--out-dir', type=Path, default=PREPROCESSING_DIR / 'results/plots')
    args = parser.parse_args()
    rows, source_sha256 = extract_metrics(args.input)
    stats = {key: box_statistics([r[key] for r in rows]) for key in METRICS}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    matplotlib_version = render_plots(rows, stats, args.out_dir)
    with (args.out_dir / 'per_schema_counts.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(source_filename=args.input.name, source_sha256=source_sha256,
                   script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   python_version=platform.python_version(), sqlite_version=sqlite3.sqlite_version,
                   matplotlib_version=matplotlib_version, examples=len(rows),
                   definitions=dict(tables='Tables declared by ddl_schema, per example',
                                    columns='Total declared columns across ddl_schema tables, per example',
                                    specification_words='len(question.split()), per example',
                                    quartiles='Linear interpolation at (n-1)*p',
                                    whiskers='Most extreme observed values inside Q1-1.5*IQR and Q3+1.5*IQR'),
                   metrics=stats)
    (args.out_dir / 'boxplot_statistics.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(f'Plotted {len(rows)} preprocessed examples: {args.out_dir / "counts_boxplots.png"}')
    for key, title in METRICS.items():
        s = stats[key]
        print(f"{title}: min={s['minimum']}, Q1={s['q1']:g}, median={s['median']:g}, Q3={s['q3']:g}, max={s['maximum']}")


if __name__ == '__main__':
    main()

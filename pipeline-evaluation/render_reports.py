#!/usr/bin/env python3
"""Render the evaluation tables and bar charts from saved metrics JSON."""

import argparse
import html
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import wrap


MATCH_REPORTS = (
    ("table_matching.png", "Mean table match by model", "mean_table_match_pct"),
    ("column_matching.png", "Mean column match by model", "mean_column_match_pct"),
)
MATCH_METHODS = {"exact": "Exact match", "similarity": "With similarity check"}
TABLE_REPORTS = (
    (
        "token_consumption.md",
        "Mean token consumption per specification",
        "mean_tokens",
        (("input", "Input tokens"), ("output", "Output tokens"), ("total", "Total tokens")),
    ),
    (
        "timings.md",
        "Mean time per specification",
        "mean_seconds",
        (("total", "Total (s)"), ("python", "Verifier and other Python work (s)"),
         ("llm", "LLM response (s)")),
    ),
)


def write_table(path, title, key, columns, summary):
    headers = ["Model", *(label for _, label in columns)]
    rows = [
        f"# {title}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---", *(["---:"] * len(columns))]) + " |",
    ]
    for model in summary["models"]:
        name = html.escape(model["model"]).replace("|", "&#124;")
        name = name.replace("\n", " ").replace("\r", " ")
        values = [model[key][field] for field, _ in columns]
        cells = [f"<code>{name}</code>", *("—" if value is None else f"{value:,.2f}" for value in values)]
        rows.append("| " + " | ".join(cells) + " |")
    if any(model[key][field] is None for model in summary["models"] for field, _ in columns):
        rows.extend(("", "— indicates that no measurement was available."))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def plot_grouped_bars(path, categories, model_values, *, xlabel, title, percentages=False):
    with TemporaryDirectory(prefix="pipeline-evaluation-matplotlib-") as config_dir:
        config_names = ("MPLCONFIGDIR", "XDG_CACHE_HOME")
        temporary_config = [name for name in config_names if name not in os.environ]
        for name in temporary_config:
            os.environ[name] = config_dir
        try:
            from matplotlib import colormaps, rc_context
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            from matplotlib.figure import Figure
            from matplotlib.ticker import MaxNLocator

            style = {
                "font.family": "DejaVu Sans",
                "font.size": 11,
                "axes.titleweight": "bold",
                "axes.labelcolor": "#334155",
                "axes.spines.top": False,
                "axes.spines.right": False,
                "xtick.color": "#334155",
                "ytick.color": "#334155",
            }
            with rc_context(style):
                legend_columns = min(len(model_values), 3)
                legend_rows = math.ceil(len(model_values) / legend_columns)
                figure = Figure(
                    figsize=(max(8.8, 7 + 0.55 * len(model_values)), 4.7 + 0.3 * legend_rows),
                    layout="constrained",
                )
                FigureCanvasAgg(figure)
                axis = figure.subplots()
                axis.set_axisbelow(True)
                axis.grid(axis="y", color="#e2e8f0", linewidth=0.8)

                positions = range(len(categories))
                width = 0.78 / len(model_values)
                colors = colormaps["tab10"].colors
                hatches = ("", "///", "\\\\", "xx")
                for index, (model, values) in enumerate(model_values):
                    offset = (index - (len(model_values) - 1) / 2) * width
                    bar_positions = [position + offset for position in positions]
                    bars = axis.bar(
                        bar_positions,
                        [math.nan if value is None else value for value in values],
                        width=width * 0.9,
                        label=model,
                        color=colors[index % len(colors)],
                        hatch=hatches[(index // len(colors)) % len(hatches)],
                    )
                    if len(model_values) <= 6:
                        axis.bar_label(bars, fmt="%.2f%%" if percentages else "%g", padding=3, fontsize=9)
                    for position, value in zip(bar_positions, values, strict=True):
                        if value is None:
                            axis.annotate(
                                "N/A", (position, 0), xytext=(0, 3), textcoords="offset points",
                                ha="center", va="bottom", fontsize=9, color="#475569",
                            )

                if percentages:
                    axis.set_xlim(-0.5, len(categories) - 0.5)
                    axis.set_ylim(0, 108)
                    axis.set_yticks(range(0, 101, 20))
                    ylabel = "Mean match per specification (%)"
                else:
                    max_count = max(max(values) for _, values in model_values)
                    axis.set_ylim(0, max(1, max_count * 1.13))
                    axis.yaxis.set_major_locator(MaxNLocator(nbins=7, integer=True))
                    ylabel = "Count of database specifications"
                axis.set_xticks(positions, categories)
                axis.set_xlabel(xlabel)
                axis.set_ylabel(ylabel)
                axis.set_title(title, pad=12)
                figure.legend(loc="outside lower center", ncols=legend_columns, frameon=False, fontsize=10)
                figure.savefig(path, dpi=180, facecolor="white", bbox_inches="tight", pad_inches=0.2)
        finally:
            for name in temporary_config:
                del os.environ[name]


def render_reports(results_dir):
    summary = json.loads((results_dir / "evaluation_metrics.json").read_text(encoding="utf-8"))
    models = summary["models"]
    if not models:
        raise ValueError("No model summaries to render")

    for filename, title, key, columns in TABLE_REPORTS:
        write_table(results_dir / filename, title, key, columns, summary)

    for filename, title, key in MATCH_REPORTS:
        plot_grouped_bars(
            results_dir / filename,
            list(MATCH_METHODS.values()),
            [(model["model"], [model[key][method] for method in MATCH_METHODS]) for model in models],
            xlabel="Matching method",
            title=title,
            percentages=True,
        )

    bins = summary["required_iteration_bins"]
    plot_grouped_bars(
        results_dir / "required_iterations.png",
        bins,
        [(model["model"], [model["required_iteration_counts"][group] for group in bins]) for model in models],
        xlabel="Required iterations",
        title="Required LLM iterations by model",
    )
    if "verification_criteria" in summary:
        criteria = summary["verification_criteria"]
        model_counts = [
            (model["model"], [model["unverified_criteria"]["failed_counts"][criterion] for criterion in criteria])
            for model in models
        ]
        plot_grouped_bars(
            results_dir / "verification_criteria_failures.png",
            ["\n".join(wrap(label, width=20)) for label in criteria.values()],
            model_counts,
            xlabel="Verification criterion",
            title="Criterion failures after exhaustion or early stop",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path, help="Directory containing evaluation_metrics.json")
    args = parser.parse_args()
    render_reports(args.results_dir)


if __name__ == "__main__":
    main()

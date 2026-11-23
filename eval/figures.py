"""Results figures: PNG charts of scored runs, for docs/results.md and the slides.

Reads the `summary.csv` of scored runs (`llm.run`) and draws:

- `boundary_f1_wall.png`, `portal_recall.png`: per reference map, one bar per method;
- `review_effect.png`: per map, the chunked pass's rule-merged answer against the reviewed
  one, one panel per agents' model (spec SC-009);
- `cost_per_map.png`, `time_per_map.png`: per map, one bar per method (two charts, never a
  second y-axis).

Colors follow the reference data-viz palette: categorical slots in fixed order, one per method,
text in text colors, recessive grid. Values are printed above the bars so identity and amount
never rest on color alone.

    python -m eval.figures   (draws the figures of the runs named in FIGURE_RUNS)
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # files only, no display
import matplotlib.pyplot as plt  # noqa: E402 - after choosing the backend

ROOT = Path(__file__).parents[1]
OUT = ROOT / "docs" / "figures"
MAPS = ["dd04_a", "dd04_d", "dd06_a", "dd07_a"]
MAP_NAMES = {"dd04_a": "tavern", "dd04_d": "tavern, no grid", "dd06_a": "mine", "dd07_a": "castle"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # categorical slots 1-4, fixed order
SURFACE, GRID = "#fcfcfb", "#e4e3de"
TEXT, TEXT_2 = "#0b0b0b", "#52514e"

# The runs the figures compare: label -> run folder under runs/ (all scored the same way).
FIGURE_RUNS = {
    "Single session, Sonnet (13.11)": "20261113-134942_quick",
    "Single session, Opus (13.11)": "20261113-135137_deep",
    "Chunked, Sonnet agents": "20261123_chunked_sonnet",
    "Chunked, Haiku agents": "20261123_chunked_haiku",
}


def read_summary(path: Path) -> dict[str, dict]:
    """A run's summary.csv as {map name: row}."""
    with Path(path).open() as f:
        return {row["map"]: row for row in csv.DictReader(f)}


def _value(row: dict | None, key: str) -> float | None:
    """A number from a summary row, or None when the map or column is missing."""
    if row is None or row.get(key) in (None, ""):
        return None
    return float(row[key])


def _style(ax, title: str, ylabel: str) -> None:
    """Recessive axes: a light horizontal grid, no box, text in text colors."""
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=TEXT, fontsize=12, pad=12)
    ax.set_ylabel(ylabel, color=TEXT_2, fontsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(TEXT_2)
    ax.tick_params(colors=TEXT_2, labelsize=9, length=0)


def _grouped_bars(ax, groups: list[str], series: dict[str, list[float | None]], fmt: str) -> None:
    """One cluster per group, one bar per series in fixed palette order, value on top.

    A missing value leaves an empty slot labelled "n/a", so a gap is never read as zero.
    """
    n = len(series)
    width = 0.8 / n
    for i, (label, values) in enumerate(series.items()):
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        heights = [v or 0 for v in values]
        bars = ax.bar(
            xs, heights, width, color=SERIES[i], label=label, edgecolor=SURFACE, linewidth=2
        )
        for bar, v in zip(bars, values, strict=True):
            text = "n/a" if v is None else format(v, fmt)
            ax.annotate(
                text,
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=7.5,
                color=TEXT_2,
            )
    ax.set_xticks(range(len(groups)), groups)


def _figure(width: float = 9, height: float = 4.2):
    """A figure on the chart surface."""
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    return fig, ax


def _save(fig, path: Path) -> Path:
    """Write a figure as a PNG and close it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def per_map_chart(
    runs: dict[str, dict[str, dict]],
    key: str,
    title: str,
    ylabel: str,
    fmt: str,
    path: Path,
    top: float | None = None,
) -> Path:
    """Grouped bars of one summary column per reference map, one bar per run."""
    fig, ax = _figure()
    series = {label: [_value(rows.get(m), key) for m in MAPS] for label, rows in runs.items()}
    _grouped_bars(ax, [MAP_NAMES[m] for m in MAPS], series, fmt)
    _style(ax, title, ylabel)
    if top is not None:
        ax.set_ylim(0, top)
    ax.legend(
        frameon=False,
        fontsize=8.5,
        labelcolor=TEXT,
        ncols=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
    )
    return _save(fig, path)


def review_chart(chunked: dict[str, dict[str, dict]], path: Path) -> Path:
    """Per map, the rule-merged answer against the reviewed one, a panel per agents' model."""
    fig, axes = plt.subplots(
        1, len(chunked), figsize=(4.6 * len(chunked), 4), facecolor=SURFACE, sharey=True
    )
    axes = axes if len(chunked) > 1 else [axes]
    for ax, (label, rows) in zip(axes, chunked.items(), strict=True):
        series = {
            "Rule merge only": [_value(rows.get(m), "merged_boundary_f1_wall") for m in MAPS],
            "After the border review": [_value(rows.get(m), "boundary_f1_wall") for m in MAPS],
        }
        _grouped_bars(ax, [MAP_NAMES[m] for m in MAPS], series, ".2f")
        _style(ax, label, "Wall boundary F1")
        ax.set_ylim(0, 1.1)
        ax.tick_params(axis="x", labelrotation=15)
    axes[0].legend(
        frameon=False,
        fontsize=8.5,
        labelcolor=TEXT,
        loc="upper center",
        bbox_to_anchor=(0.5 * len(chunked) + 0.05 * (len(chunked) - 1), -0.18),
        ncols=2,
    )
    for ax in axes[1:]:
        ax.set_ylabel("")  # the y-axis is shared; label it once
    fig.suptitle(
        "Does the orchestrator's border review help?",
        x=0.02,
        y=1.04,
        ha="left",
        color=TEXT,
        fontsize=13,
    )
    return _save(fig, path)


def make_figures(runs: dict[str, Path], out: Path = OUT) -> list[Path]:
    """Draw every figure from the runs given as {label: path to summary.csv}.

    Runs whose summary has `merged_boundary_f1_wall` (chunked runs) also go into the review
    chart. Returns the paths written.
    """
    rows = {label: read_summary(path) for label, path in runs.items()}
    written = [
        per_map_chart(
            rows,
            "boundary_f1_wall",
            "Wall boundary F1 per reference map",
            "Boundary F1 (0.1-square tolerance)",
            ".2f",
            out / "boundary_f1_wall.png",
            top=1.1,
        ),
        per_map_chart(
            rows,
            "portal_recall",
            "Doors and windows found per reference map",
            "Portal recall",
            ".2f",
            out / "portal_recall.png",
            top=1.1,
        ),
        per_map_chart(
            rows,
            "cost_usd",
            "Estimated cost per map",
            "US dollars",
            ".2f",
            out / "cost_per_map.png",
        ),
        per_map_chart(rows, "seconds", "Time per map", "Seconds", ".0f", out / "time_per_map.png"),
    ]
    chunked = {
        label: r
        for label, r in rows.items()
        if any(row.get("merged_boundary_f1_wall") for row in r.values())
    }
    if chunked:
        written.append(review_chart(chunked, out / "review_effect.png"))
    return written


def main() -> None:
    """Draw the figures for the runs in FIGURE_RUNS that exist under runs/."""
    runs = {
        label: ROOT / "runs" / name / "summary.csv"
        for label, name in FIGURE_RUNS.items()
        if (ROOT / "runs" / name / "summary.csv").exists()
    }
    for path in make_figures(runs):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()

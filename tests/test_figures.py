"""The results figures: drawn from small summary files, no model and no paid call."""

import csv

from PIL import Image

from eval.figures import MAPS, make_figures, read_summary


def write_summary(path, rows: list[dict]) -> None:
    """Write rows as a summary.csv, the way llm.run does."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_every_figure_is_drawn_and_the_review_chart_only_for_chunked_runs(tmp_path):
    """Two runs, one chunked: five PNGs, each a real image; a missing map is not an error."""
    single = tmp_path / "single" / "summary.csv"
    chunked = tmp_path / "chunked" / "summary.csv"
    write_summary(
        single,
        [
            {
                "map": m,
                "boundary_f1_wall": 0.8,
                "portal_recall": 0.5,
                "cost_usd": 0.1,
                "seconds": 20,
            }
            for m in MAPS[:3]
        ],
    )
    write_summary(
        chunked,
        [
            {
                "map": m,
                "boundary_f1_wall": 0.9,
                "merged_boundary_f1_wall": 0.85,
                "portal_recall": 0.6,
                "cost_usd": 0.3,
                "seconds": 45,
            }
            for m in MAPS
        ],
    )
    out = tmp_path / "figures"
    written = make_figures({"Single": single, "Chunked": chunked}, out)
    names = sorted(p.name for p in written)
    assert names == [
        "boundary_f1_wall.png",
        "cost_per_map.png",
        "portal_recall.png",
        "review_effect.png",
        "time_per_map.png",
    ]
    for path in written:
        with Image.open(path) as image:
            assert image.width > 500 and image.height > 300
    only_single = make_figures({"Single": single}, tmp_path / "plain")
    assert "review_effect.png" not in [p.name for p in only_single]


def test_read_summary_keys_rows_by_map(tmp_path):
    """A summary is read as {map: row}."""
    path = tmp_path / "s.csv"
    write_summary(path, [{"map": "dd04_a", "cost_usd": 0.1}])
    assert read_summary(path)["dd04_a"]["cost_usd"] == "0.1"

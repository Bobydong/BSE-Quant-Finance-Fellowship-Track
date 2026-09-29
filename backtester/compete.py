"""Competition runner.

Runs every submitted strategy against a dataset - including one the fellows
have never seen - and writes a ranked leaderboard.

Usage:
    python compete.py --submissions submissions/ --data HELDOUT --fee 10
    python compete.py --submissions submissions/ --data BCH-1d --html leaderboard.html

Each submission is a .py file containing one or more Strategy subclasses.
Because every strategy implements the same interface, they can all be run
identically without touching anyone's code.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import sys
import traceback
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bsequant as bq
from bsequant.strategy import Strategy


def load_from_file(path: Path) -> list[type]:
    """Import a .py file and return the Strategy subclasses it defines."""
    spec = importlib.util.spec_from_file_location(f"sub_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [obj for _, obj in inspect.getmembers(mod, inspect.isclass)
            if issubclass(obj, Strategy) and obj is not Strategy
            and obj.__module__ == mod.__name__]


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the strategy competition.")
    ap.add_argument("--submissions", default="submissions",
                    help="folder of .py files, one per fellow")
    ap.add_argument("--data", default="BCH-1d", help="dataset name")
    ap.add_argument("--fee", type=float, default=10.0, help="fee in bps per side")
    ap.add_argument("--periods-per-year", type=int, default=None,
                    help="annualization factor (365 crypto, 252 equities). "
                         "Inferred from the data when omitted.")
    ap.add_argument("--csv", default="leaderboard.csv")
    ap.add_argument("--html", default=None, help="also write an HTML leaderboard")
    args = ap.parse_args()

    data = bq.load(args.data)
    ppy = args.periods_per_year or bq.infer_periods_per_year(data)
    folder = Path(args.submissions)
    files = sorted(folder.glob("*.py")) if folder.exists() else []

    if not files:
        print(f"No .py files in {folder}/")
        return

    print(f"Dataset {args.data}: {len(data):,} days "
          f"({data.index[0].date()} → {data.index[-1].date()})")
    print(f"Fee: {args.fee} bps per side | annualizing by sqrt({ppy})\n")

    rows = []
    for path in files:
        author = path.stem
        try:
            classes = load_from_file(path)
        except Exception:                                  # noqa: BLE001
            print(f"  ✗ {author}: failed to import")
            traceback.print_exc(limit=1)
            continue

        if not classes:
            print(f"  ✗ {author}: no Strategy subclass found")
            continue

        for cls in classes:
            try:
                res = bq.run(cls(), data, fee_bps=args.fee,
                             periods_per_year=ppy)
            except Exception as exc:                       # noqa: BLE001
                print(f"  ✗ {author}/{cls.__name__}: {exc}")
                continue

            m = res.metrics
            flagged = any("LOOKAHEAD" in w or "WIPED OUT" in w for w in res.warnings)
            rows.append({
                "author": author,
                "strategy": cls.name,
                "total_return": m["total_return"],
                "sharpe": m["sharpe"],
                "max_drawdown": m["max_drawdown"],
                "win_rate": m["win_rate"],
                "trades": m["trades"],
                "flagged": "⚠️" if flagged else "",
            })
            flag = "  ⚠️ " + res.warnings[0][:60] if flagged else ""
            print(f"  ✓ {author:<18} {cls.name:<28} "
                  f"Sharpe {m['sharpe']:>6.2f}  return {m['total_return']:>8.1%}{flag}")

    if not rows:
        print("\nNothing ran successfully.")
        return

    # Ranked by Sharpe, not raw return - risk-adjusted performance is the
    # thing worth rewarding, and it is harder to game with leverage.
    board = (pd.DataFrame(rows)
             .sort_values("sharpe", ascending=False)
             .reset_index(drop=True))
    board.index += 1
    board.index.name = "rank"

    print("\n" + "=" * 78)
    print("LEADERBOARD".center(78))
    print("=" * 78)
    print(board.to_string(formatters={
        "total_return": "{:.1%}".format, "sharpe": "{:.2f}".format,
        "max_drawdown": "{:.1%}".format, "win_rate": "{:.1%}".format}))

    board.to_csv(args.csv)
    print(f"\nWrote {args.csv}")

    if args.html:
        html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>BSE Quant Leaderboard</title>
<style>
 body{{background:#0D1117;color:#E6EDF3;font-family:system-ui,sans-serif;
       max-width:1000px;margin:3rem auto;padding:0 1.5rem}}
 h1{{font-weight:600}} .meta{{color:#8B98A5;margin-bottom:2rem}}
 table{{width:100%;border-collapse:collapse}}
 th{{text-align:left;color:#8B98A5;font-weight:500;font-size:.85rem;
     text-transform:uppercase;letter-spacing:.05em;padding:.6rem .8rem;
     border-bottom:1px solid #30363D}}
 td{{padding:.7rem .8rem;border-bottom:1px solid #21262D}}
 tr:nth-child(1) td{{background:#12352a}}
 .pos{{color:#1D9E75}} .neg{{color:#D8503A}}
</style></head><body>
<h1>Leaderboard</h1>
<div class="meta">{args.data} &middot; {len(data):,} days &middot;
{data.index[0].date()} to {data.index[-1].date()} &middot;
{args.fee} bps per side &middot; &radic;{ppy} annualization &middot; ranked by Sharpe</div>
<table><tr><th>#</th><th>Author</th><th>Strategy</th><th>Sharpe</th>
<th>Return</th><th>Max DD</th><th>Trades</th><th></th></tr>
"""
        for rank, r in board.iterrows():
            cls_s = "pos" if r["sharpe"] > 0 else "neg"
            cls_r = "pos" if r["total_return"] > 0 else "neg"
            html += (f'<tr><td>{rank}</td><td>{r["author"]}</td>'
                     f'<td>{r["strategy"]}</td>'
                     f'<td class="{cls_s}">{r["sharpe"]:.2f}</td>'
                     f'<td class="{cls_r}">{r["total_return"]:.1%}</td>'
                     f'<td>{r["max_drawdown"]:.1%}</td>'
                     f'<td>{r["trades"]:,}</td><td>{r["flagged"]}</td></tr>\n')
        html += "</table></body></html>"
        Path(args.html).write_text(html)
        print(f"Wrote {args.html}")


if __name__ == "__main__":
    main()

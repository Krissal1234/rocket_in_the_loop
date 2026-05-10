#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


LOGS_DIR_DEFAULT = Path(__file__).parent / "../logs"
OUT_DIR_DEFAULT  = Path(__file__).parent / "../results"

RE_APOGEE = re.compile(r"APOGEE\s+([\d.]+)\s+([\d.]+)")
RE_DROGUE  = re.compile(r"DROGUE\s+([\d.]+)")
RE_MAIN    = re.compile(r"MAIN\s+([\d.]+)")
RE_DEP     = re.compile(r"DEP\s+([\d.]+)\s+([\d.]+)")


def parse_log(path: Path) -> dict | None:
    text = path.read_text()

    apogee_m = apogee_m = drogue = main = None
    dep_series = []

    for line in text.splitlines():
        if apogee_m is None:
            m = RE_APOGEE.search(line)
            if m:
                apogee_m = float(m.group(1))

        if drogue is None:
            m = RE_DROGUE.search(line)
            if m:
                drogue = float(m.group(1))

        if main is None:
            m = RE_MAIN.search(line)
            if m:
                main = float(m.group(1))

        m = RE_DEP.search(line)
        if m:
            dep_series.append((float(m.group(1)), float(m.group(2))))

    # Skip incomplete logs
    if apogee_m is None or drogue is None or main is None:
        print(f"  WARNING: incomplete log skipped: {path.name}")
        return None

    return {
        "apogee_m":   apogee_m,
        "drogue_s":   drogue,
        "main_s":     main,
        "dep_series": dep_series,
    }


def load_runs(logs_dir: Path, mode: str) -> list[dict]:
    files = sorted(logs_dir.glob(f"{mode}_*.log"))
    if not files:
        print(f"  No {mode} log files found in {logs_dir}")
        return []
    runs = []
    for f in files:
        result = parse_log(f)
        if result is not None:
            result["run_id"] = f.stem
            runs.append(result)
    print(f"  Loaded {len(runs)} valid {mode} runs from {len(files)} files.")
    return runs




def summary_stats(values: list[float], name: str) -> dict:
    arr = np.array(values)
    return {
        "metric": name,
        "n":      len(arr),
        "mean":   arr.mean(),
        "std":    arr.std(ddof=1),
        "min":    arr.min(),
        "max":    arr.max(),
    }


def run_ttest(a: list[float], b: list[float], label: str):
    t, p = stats.ttest_ind(a, b, equal_var=False)
    print(f"  {label:30s}  t={t:+.4f}  p={p:.4f}  {'*SIGNIFICANT*' if p < 0.05 else 'not significant'}")
    return t, p


def interpolate_dep(dep_series: list[tuple], t_grid: np.ndarray) -> np.ndarray:
    if not dep_series:
        return np.zeros_like(t_grid)
    ts = np.array([d[0] for d in dep_series])
    vs = np.array([d[1] for d in dep_series])
    return np.interp(t_grid, ts, vs, left=0.0, right=0.0)



COLORS = {
    "nonsil": "#2196F3",   # blue
    "sil":    "#F44336",   # red
}

LABELS = {
    "nonsil": "Non-SIL",
    "sil":    "SIL",
}


def plot_summary_bars(sil_runs, nonsil_runs, out_dir: Path):
    """Bar chart comparing mean ± std for apogee, drogue, main."""
    metrics = ["apogee_m", "drogue_s", "main_s"]
    ylabels = ["Apogee AGL (m)", "Drogue ejection time (s)", "Main ejection time (s)"]
    titles  = ["Apogee", "Drogue Deployment", "Main Deployment"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle("SIL vs Non-SIL: Mean ± Std Dev", fontsize=14, fontweight="bold")

    for ax, metric, ylabel, title in zip(axes, metrics, ylabels, titles):
        for mode, runs in [("nonsil", nonsil_runs), ("sil", sil_runs)]:
            vals = [r[metric] for r in runs]
            mean, std = np.mean(vals), np.std(vals, ddof=1)
            ax.bar(LABELS[mode], mean, yerr=std, color=COLORS[mode],
                   alpha=0.8, capsize=6, width=0.5, label=LABELS[mode])
            ax.scatter([LABELS[mode]] * len(vals), vals,
                       color="black", s=15, zorder=5, alpha=0.5)

        ax.set_title(title, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    path = out_dir / "summary_bars.png"
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_dep_individual(sil_runs, nonsil_runs, out_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    fig.suptitle("Deployment Level — All Individual Runs", fontsize=14, fontweight="bold")

    for ax, mode, runs in zip(axes, ["nonsil", "sil"], [nonsil_runs, sil_runs]):
        for r in runs:
            if not r["dep_series"]:
                continue
            ts = [d[0] for d in r["dep_series"]]
            vs = [d[1] for d in r["dep_series"]]
            ax.plot(ts, vs, color=COLORS[mode], alpha=0.35, linewidth=0.8)

        ax.set_title(LABELS[mode], fontweight="bold")
        ax.set_xlabel("Simulation time (s)")
        ax.set_ylabel("Deployment level")
        ax.set_ylim(-0.05, 1.05)
        ax.grid(linestyle="--", alpha=0.4)

    plt.tight_layout()
    path = out_dir / "dep_individual.png"
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_dep_mean_band(sil_runs, nonsil_runs, out_dir: Path):
    all_ts = []
    for runs in [sil_runs, nonsil_runs]:
        for r in runs:
            if r["dep_series"]:
                all_ts.extend([d[0] for d in r["dep_series"]])

    if not all_ts:
        print("  No deployment data to plot.")
        return

    t_min = min(all_ts)
    t_max = max(all_ts)
    t_grid = np.linspace(t_min, t_max, 500)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle("Deployment Level — Mean ± 1 Std Dev", fontsize=14, fontweight="bold")

    for mode, runs in [("nonsil", nonsil_runs), ("sil", sil_runs)]:
        interps = np.array([interpolate_dep(r["dep_series"], t_grid) for r in runs])
        mean = interps.mean(axis=0)
        std  = interps.std(axis=0, ddof=1)

        ax.plot(t_grid, mean, color=COLORS[mode], linewidth=2, label=LABELS[mode])
        ax.fill_between(t_grid, mean - std, mean + std,
                        color=COLORS[mode], alpha=0.2)

    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Deployment level")
    ax.set_ylim(-0.05, 1.05)
    ax.legend()
    ax.grid(linestyle="--", alpha=0.4)

    plt.tight_layout()
    path = out_dir / "dep_mean_band.png"
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_apogee_scatter(sil_runs, nonsil_runs, out_dir: Path):
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.suptitle("Apogee AGL per Run", fontsize=14, fontweight="bold")

    for mode, runs in [("nonsil", nonsil_runs), ("sil", sil_runs)]:
        vals = [r["apogee_m"] for r in runs]
        xs   = range(1, len(vals) + 1)
        ax.scatter(xs, vals, color=COLORS[mode], label=LABELS[mode], s=40, zorder=5)
        ax.axhline(np.mean(vals), color=COLORS[mode], linestyle="--", linewidth=1, alpha=0.7)

    ax.set_xlabel("Run number")
    ax.set_ylabel("Apogee AGL (m)")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.4)

    plt.tight_layout()
    path = out_dir / "apogee_scatter.png"
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()



def main():
    parser = argparse.ArgumentParser(description="SIL vs Non-SIL comparative analysis")
    parser.add_argument("--logs", type=Path, default=LOGS_DIR_DEFAULT,
                        help="Path to logs directory")
    parser.add_argument("--out",  type=Path, default=OUT_DIR_DEFAULT,
                        help="Output directory for plots and CSV")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    print(f"\nLoading logs from: {args.logs.resolve()}")
    nonsil_runs = load_runs(args.logs, "nonsil")
    sil_runs    = load_runs(args.logs, "sil")

    if not nonsil_runs and not sil_runs:
        print("No valid runs found. Exiting.")
        sys.exit(1)

    print("\n── Summary Statistics ───────────────────────────────────")
    rows = []
    for mode, runs in [("nonsil", nonsil_runs), ("sil", sil_runs)]:
        if not runs:
            continue
        for metric, label in [("apogee_m", "Apogee AGL (m)"),
                               ("drogue_s", "Drogue time (s)"),
                               ("main_s",   "Main time (s)")]:
            s = summary_stats([r[metric] for r in runs], label)
            s["mode"] = mode
            rows.append(s)
            print(f"  [{mode:6s}] {label:20s}  "
                  f"n={s['n']}  mean={s['mean']:.3f}  std={s['std']:.4f}  "
                  f"min={s['min']:.3f}  max={s['max']:.3f}")

    summary_df = pd.DataFrame(rows)[["mode", "metric", "n", "mean", "std", "min", "max"]]
    csv_path = args.out / "summary_stats.csv"
    summary_df.to_csv(csv_path, index=False)
    print(f"\n  Summary saved: {csv_path}")

    # ── T-tests ───────────────────────────────────────────────────────────────
    if sil_runs and nonsil_runs:
        print("\n── Welch's T-Tests (SIL vs Non-SIL) ────────────────────")
        ttest_rows = []
        for metric, label in [("apogee_m", "Apogee AGL (m)"),
                               ("drogue_s", "Drogue time (s)"),
                               ("main_s",   "Main time (s)")]:
            a = [r[metric] for r in nonsil_runs]
            b = [r[metric] for r in sil_runs]
            t, p = run_ttest(a, b, label)
            ttest_rows.append({"metric": label, "t": t, "p": p,
                                "significant": p < 0.05})

        ttest_df = pd.DataFrame(ttest_rows)
        ttest_path = args.out / "ttest_results.csv"
        ttest_df.to_csv(ttest_path, index=False)
        print(f"  T-test results saved: {ttest_path}")

    print("\n── Generating Plots ─────────────────────────────────────")
    if sil_runs and nonsil_runs:
        plot_summary_bars(sil_runs, nonsil_runs, args.out)
        plot_apogee_scatter(sil_runs, nonsil_runs, args.out)
        plot_dep_individual(sil_runs, nonsil_runs, args.out)
        plot_dep_mean_band(sil_runs, nonsil_runs, args.out)
    elif sil_runs:
        print("  Only SIL runs found — skipping comparative plots.")
    elif nonsil_runs:
        print("  Only Non-SIL runs found — skipping comparative plots.")

    print(f"\nDone. Results in: {args.out.resolve()}\n")


if __name__ == "__main__":
    main()
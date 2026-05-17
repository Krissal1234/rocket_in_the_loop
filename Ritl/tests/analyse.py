#!/usr/bin/env python3
"""
Analysis script for rocket_in_the_loop thesis experiments.

Compares architectures against the Non-SIL baseline.
Supports rate group frequency sweep comparison.

Usage:
    # basic SIL vs Non-SIL (old style)
    python analyse.py

    # compare specific architecture against baseline
    python analyse.py --compare sensordriven_calisto nonsil_calisto

    # rate group frequency sweep
    python analyse.py --rategroup-sweep --rocket calisto

    # full architecture comparison
    python analyse.py --arch-compare --rocket calisto
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt


LOGS_DIR_DEFAULT = Path(__file__).parent / "../logs"
OUT_DIR_DEFAULT  = Path(__file__).parent / "../results"

RE_APOGEE    = re.compile(r"APOGEE\s+([\d.]+)\s+([\d.]+)")
RE_DROGUE    = re.compile(r"DROGUE\s+([\d.]+)")
RE_MAIN      = re.compile(r"MAIN\s+([\d.]+)")
RE_DEP       = re.compile(r"DEP\s+([\d.]+)\s+([\d.]+)")
RE_STALENESS = re.compile(r"STALENESS\s+([\d.]+)\s+([\d.]+)")
RE_WALL_TIME = re.compile(r"WALL_TIME\s+([\d.]+)")

T_GRID = np.linspace(3.3, 8.0, 500)

ARCH_COLORS = {
    "nonsil":         "#2196F3",   # blue
    "sensordriven":   "#4CAF50",   # green
    "lockstep":       "#9C27B0",   # purple
    "rategroup_1hz":  "#D32F2F",   # dark red
    "rategroup_5hz":  "#E65100",   # deep orange
    "rategroup_10hz": "#F9A825",   # amber
    "rategroup_25hz": "#00897B",   # teal
    "rategroup_50hz": "#C62828",   # crimson
}

ARCH_LABELS = {
    "nonsil":         "Non-SIL (baseline)",
    "sensordriven":   "Sensor Driven",
    "lockstep":       "Control Lockstep",
    "rategroup_1hz":  "Rate Group 1 Hz",
    "rategroup_5hz":  "Rate Group 5 Hz",
    "rategroup_10hz": "Rate Group 10 Hz",
    "rategroup_25hz": "Rate Group 25 Hz",
    "rategroup_50hz": "Rate Group 50 Hz",
}


# ── parsing ───────────────────────────────────────────────────────────────────

def parse_log(path: Path) -> dict | None:
    text = path.read_text()
    apogee_m = drogue = main = wall_time = None
    dep_series = []
    staleness_values = []

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
        if wall_time is None:
            m = RE_WALL_TIME.search(line)
            if m:
                wall_time = float(m.group(1))
        m = RE_DEP.search(line)
        if m:
            dep_series.append((float(m.group(1)), float(m.group(2))))
        m = RE_STALENESS.search(line)
        if m:
            staleness_values.append(float(m.group(2)))

    if apogee_m is None or drogue is None or main is None:
        print(f"  WARNING: incomplete log skipped: {path.name}")
        return None

    return {
        "apogee_m":       apogee_m,
        "drogue_s":       drogue,
        "main_s":         main,
        "dep_series":     dep_series,
        "wall_time":      wall_time,
        "mean_staleness": float(np.mean(staleness_values)) if staleness_values else None,
        "max_staleness":  float(np.max(staleness_values))  if staleness_values else None,
    }


def load_runs(logs_dir: Path, prefix: str) -> list[dict]:
    """Load all runs matching logs_dir/<prefix>_*.log"""
    files = sorted(logs_dir.glob(f"{prefix}_*.log"))
    if not files:
        print(f"  No runs found for prefix '{prefix}'")
        return []
    runs = []
    for f in files:
        result = parse_log(f)
        if result is not None:
            result["run_id"] = f.stem
            runs.append(result)
    print(f"  [{prefix}] loaded {len(runs)} valid runs from {len(files)} files.")
    return runs


def arch_key(prefix: str) -> str:
    """Extract architecture key from prefix for colour/label lookup.
    e.g. 'rategroup_10hz_calisto' -> 'rategroup_10hz'
         'sensordriven_calisto'   -> 'sensordriven'
         'nonsil_calisto'         -> 'nonsil'
    """
    parts = prefix.replace("_calisto", "").replace("_cameos", "")
    return parts


# ── metrics ───────────────────────────────────────────────────────────────────

def interpolate_dep(dep_series, t_grid):
    if not dep_series:
        return np.zeros_like(t_grid)
    ts = np.array([d[0] for d in dep_series])
    vs = np.array([d[1] for d in dep_series])
    return np.interp(t_grid, ts, vs, left=0.0, right=0.0)


def compute_dep_rmse(runs, baseline):
    return [float(np.sqrt(np.mean((interpolate_dep(r["dep_series"], T_GRID) - baseline) ** 2)))
            for r in runs]


def summary_stats(values, name):
    arr = np.array(values)
    return {
        "metric": name,
        "n":      len(arr),
        "mean":   float(arr.mean()),
        "std":    float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "min":    float(arr.min()),
        "max":    float(arr.max()),
    }


def run_ttest(a, b, label):
    if len(a) < 2 or len(b) < 2:
        print(f"  {label:40s}  (skipped — need ≥2 runs)")
        return None, None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    sig = "*SIGNIFICANT*" if p < 0.05 else "not significant"
    print(f"  {label:40s}  t={t:+.4f}  p={p:.4f}  {sig}")
    return t, p


# ── printing ──────────────────────────────────────────────────────────────────

def print_summary(prefix, runs, nonsil_dep_baseline):
    key = arch_key(prefix)
    label = ARCH_LABELS.get(key, prefix)
    print(f"\n── {label}  (n={len(runs)}) {'─'*30}")

    for metric, mname in [("apogee_m", "Apogee AGL (m)"),
                           ("drogue_s", "Drogue time (s)"),
                           ("main_s",   "Main time (s)")]:
        vals = [r[metric] for r in runs]
        s = summary_stats(vals, mname)
        print(f"  {mname:20s}  mean={s['mean']:.3f}  std={s['std']:.4f}  "
              f"min={s['min']:.3f}  max={s['max']:.3f}")

    if nonsil_dep_baseline is not None and key != "nonsil":
        rmses = compute_dep_rmse(runs, nonsil_dep_baseline)
        s = summary_stats(rmses, "DEP RMSE")
        print(f"  {'DEP RMSE':20s}  mean={s['mean']:.4f}  std={s['std']:.4f}  "
              f"max={s['max']:.4f}")

    wall_times = [r["wall_time"] for r in runs if r["wall_time"] is not None]
    if wall_times:
        s = summary_stats(wall_times, "Wall time (s)")
        print(f"  {'Wall time (s)':20s}  mean={s['mean']:.2f}  std={s['std']:.2f}")

    staleness_runs = [r for r in runs if r["mean_staleness"] is not None]
    if staleness_runs:
        mean_s = [r["mean_staleness"] for r in staleness_runs]
        max_s  = [r["max_staleness"]  for r in staleness_runs]
        print(f"  {'Mean staleness (s)':20s}  mean={np.mean(mean_s):.4f}  "
              f"max={np.max(mean_s):.4f}")


# ── plots ─────────────────────────────────────────────────────────────────────

def color(prefix):
    return ARCH_COLORS.get(arch_key(prefix), "#888888")


def label(prefix):
    return ARCH_LABELS.get(arch_key(prefix), prefix)


def plot_apogee_comparison(runs_by_prefix, nonsil_mean, out_dir, filename, title):
    """Bar chart of mean apogee ± std for each architecture."""
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for i, (prefix, runs) in enumerate(runs_by_prefix.items()):
        vals = [r["apogee_m"] for r in runs]
        mean = np.mean(vals)
        std  = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
        ax.bar(label(prefix), mean, yerr=std, color=color(prefix),
               alpha=0.8, capsize=6, width=0.6)
        ax.scatter([label(prefix)] * len(vals), vals,
                   color="black", s=15, zorder=5, alpha=0.5)

    if nonsil_mean is not None:
        ax.axhline(nonsil_mean, color=ARCH_COLORS["nonsil"],
                   linestyle="--", linewidth=1.5, label="Non-SIL baseline")
        ax.legend()

    ax.set_ylabel("Apogee AGL (m)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    path = out_dir / filename
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_dep_rmse_comparison(runs_by_prefix, nonsil_dep_baseline, out_dir, filename, title):
    """DEP RMSE per architecture vs Non-SIL baseline."""
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for prefix, runs in runs_by_prefix.items():
        if arch_key(prefix) == "nonsil":
            continue
        rmses = compute_dep_rmse(runs, nonsil_dep_baseline)
        mean  = np.mean(rmses)
        std   = np.std(rmses, ddof=1) if len(rmses) > 1 else 0.0
        ax.bar(label(prefix), mean, yerr=std, color=color(prefix),
               alpha=0.8, capsize=6, width=0.6)
        ax.scatter([label(prefix)] * len(rmses), rmses,
                   color="black", s=15, zorder=5, alpha=0.5)

    ax.set_ylabel("DEP RMSE (deployment level)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    path = out_dir / filename
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_wall_time_comparison(runs_by_prefix, out_dir, filename, title):
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for prefix, runs in runs_by_prefix.items():
        wts = [r["wall_time"] for r in runs if r["wall_time"] is not None]
        if not wts:
            continue
        mean = np.mean(wts)
        std  = np.std(wts, ddof=1) if len(wts) > 1 else 0.0
        ax.bar(label(prefix), mean, yerr=std, color=color(prefix),
               alpha=0.8, capsize=6, width=0.6)
        ax.scatter([label(prefix)] * len(wts), wts,
                   color="black", s=15, zorder=5, alpha=0.5)

    ax.set_ylabel("Wall-clock time (s)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    path = out_dir / filename
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_dep_overlay(runs_by_prefix, out_dir, filename, title):
    """DEP curves mean ± std band for each architecture."""
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for prefix, runs in runs_by_prefix.items():
        interps = np.array([interpolate_dep(r["dep_series"], T_GRID) for r in runs])
        mean = interps.mean(axis=0)
        std  = interps.std(axis=0, ddof=1) if len(runs) > 1 else np.zeros_like(mean)
        ax.plot(T_GRID, mean, color=color(prefix), linewidth=2, label=label(prefix))
        ax.fill_between(T_GRID, mean - std, mean + std, color=color(prefix), alpha=0.15)

    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Deployment level")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=8)
    ax.grid(linestyle="--", alpha=0.4)
    plt.tight_layout()
    path = out_dir / filename
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()


def plot_trajectory_overlay(runs_by_prefix, logs_dir, out_dir, filename, title):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for prefix, runs in runs_by_prefix.items():
        for i, r in enumerate(runs):
            traj_path = logs_dir / f"{r['run_id']}_trajectory.csv"
            if not traj_path.exists():
                continue
            data = np.loadtxt(traj_path, delimiter=",", skiprows=1)
            t, alt, vz = data[:, 0], data[:, 1], data[:, 2]
            lbl = label(prefix) if i == 0 else None
            ax1.plot(t, alt, color=color(prefix), alpha=0.4, linewidth=0.8, label=lbl)
            ax2.plot(t, vz,  color=color(prefix), alpha=0.4, linewidth=0.8)

    ax1.set_ylabel("Altitude AGL (m)")
    ax1.legend(fontsize=8)
    ax1.grid(linestyle="--", alpha=0.4)
    ax2.set_ylabel("Vertical velocity (m/s)")
    ax2.set_xlabel("Simulation time (s)")
    ax2.grid(linestyle="--", alpha=0.4)
    plt.tight_layout()
    path = out_dir / filename
    plt.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.close()



def export_all_runs_csv(runs_by_prefix, nonsil_dep_baseline, out_dir):
    rows = []
    for prefix, runs in runs_by_prefix.items():
        rmses = compute_dep_rmse(runs, nonsil_dep_baseline) \
                if nonsil_dep_baseline is not None and arch_key(prefix) != "nonsil" \
                else [None] * len(runs)
        for r, rmse in zip(runs, rmses):
            rows.append({
                "prefix":          prefix,
                "run_id":          r["run_id"],
                "apogee_m":        r["apogee_m"],
                "drogue_s":        r["drogue_s"],
                "main_s":          r["main_s"],
                "wall_time_s":     r["wall_time"],
                "dep_rmse":        rmse,
                "mean_staleness":  r["mean_staleness"],
                "max_staleness":   r["max_staleness"],
            })
    path = out_dir / "all_runs.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  Saved: {path}")


# ── modes ─────────────────────────────────────────────────────────────────────

def run_arch_compare(logs_dir, out_dir, rocket):
    """Compare all architectures against non-sil baseline."""
    prefixes = [
        f"nonsil_{rocket}",
        f"sensordriven_{rocket}",
        f"lockstep_{rocket}",
        f"rategroup_10hz_{rocket}",   # representative rate
    ]

    runs_by_prefix = {}
    for p in prefixes:
        runs = load_runs(logs_dir, p)
        if runs:
            runs_by_prefix[p] = runs

    if not runs_by_prefix:
        print("No runs found.")
        return

    nonsil_key = f"nonsil_{rocket}"
    nonsil_runs = runs_by_prefix.get(nonsil_key, [])
    nonsil_dep_baseline = interpolate_dep(
        nonsil_runs[0]["dep_series"], T_GRID) if nonsil_runs else None
    nonsil_mean = np.mean([r["apogee_m"] for r in nonsil_runs]) if nonsil_runs else None

    for prefix, runs in runs_by_prefix.items():
        print_summary(prefix, runs, nonsil_dep_baseline)

    print("\n── Generating Plots ─────────────────────────────────────")
    plot_apogee_comparison(runs_by_prefix, nonsil_mean, out_dir,
                           "arch_apogee.png", "Apogee by Architecture")
    if nonsil_dep_baseline is not None:
        plot_dep_rmse_comparison(runs_by_prefix, nonsil_dep_baseline, out_dir,
                                 "arch_dep_rmse.png", "DEP RMSE by Architecture")
    plot_wall_time_comparison(runs_by_prefix, out_dir,
                              "arch_wall_time.png", "Wall Time by Architecture")
    plot_dep_overlay(runs_by_prefix, out_dir,
                     "arch_dep_overlay.png", "Airbrake Deployment by Architecture")
    plot_trajectory_overlay(runs_by_prefix, logs_dir, out_dir,
                            "arch_trajectory.png", "Trajectory by Architecture")
    export_all_runs_csv(runs_by_prefix, nonsil_dep_baseline, out_dir)


def run_rategroup_sweep(logs_dir, out_dir, rocket):
    """Compare rate group frequencies against non-sil baseline."""
    prefixes = [
        f"nonsil_{rocket}",
        f"rategroup_1hz_{rocket}",
        f"rategroup_5hz_{rocket}",
        f"rategroup_10hz_{rocket}",
        f"rategroup_25hz_{rocket}",
        f"rategroup_50hz_{rocket}",
    ]

    runs_by_prefix = {}
    for p in prefixes:
        runs = load_runs(logs_dir, p)
        if runs:
            runs_by_prefix[p] = runs

    if not runs_by_prefix:
        print("No runs found.")
        return

    nonsil_key = f"nonsil_{rocket}"
    nonsil_runs = runs_by_prefix.get(nonsil_key, [])
    nonsil_dep_baseline = interpolate_dep(
        nonsil_runs[0]["dep_series"], T_GRID) if nonsil_runs else None
    nonsil_mean = np.mean([r["apogee_m"] for r in nonsil_runs]) if nonsil_runs else None

    for prefix, runs in runs_by_prefix.items():
        print_summary(prefix, runs, nonsil_dep_baseline)

    # additional: apogee error vs frequency line plot
    rg_prefixes = [p for p in prefixes if "rategroup" in p and p in runs_by_prefix]
    if rg_prefixes and nonsil_mean is not None:
        freqs  = [int(re.search(r"(\d+)hz", p).group(1)) for p in rg_prefixes]
        errors = [abs(np.mean([r["apogee_m"] for r in runs_by_prefix[p]]) - nonsil_mean)
                  for p in rg_prefixes]
        rmses  = [np.mean(compute_dep_rmse(runs_by_prefix[p], nonsil_dep_baseline))
                  for p in rg_prefixes] if nonsil_dep_baseline is not None else None

        fig, axes = plt.subplots(1, 2 if rmses else 1, figsize=(12, 5))
        if not isinstance(axes, np.ndarray):
            axes = [axes]

        fig.suptitle("Rate Group Frequency vs Fidelity", fontsize=14, fontweight="bold")

        axes[0].plot(freqs, errors, "o-", color="#F44336", linewidth=2, markersize=8)
        axes[0].set_xlabel("Rate group frequency (Hz)")
        axes[0].set_ylabel("Apogee error vs baseline (m)")
        axes[0].set_title("Apogee Error")
        axes[0].grid(linestyle="--", alpha=0.4)

        if rmses:
            axes[1].plot(freqs, rmses, "o-", color="#FF9800", linewidth=2, markersize=8)
            axes[1].set_xlabel("Rate group frequency (Hz)")
            axes[1].set_ylabel("DEP RMSE")
            axes[1].set_title("Airbrake Control Error")
            axes[1].grid(linestyle="--", alpha=0.4)

        plt.tight_layout()
        path = out_dir / "rategroup_sweep.png"
        plt.savefig(path, dpi=150)
        print(f"  Saved: {path}")
        plt.close()

    print("\n── Generating Plots ─────────────────────────────────────")
    plot_apogee_comparison(runs_by_prefix, nonsil_mean, out_dir,
                           "rg_apogee.png", "Apogee by Rate Group Frequency")
    if nonsil_dep_baseline is not None:
        plot_dep_rmse_comparison(runs_by_prefix, nonsil_dep_baseline, out_dir,
                                 "rg_dep_rmse.png", "DEP RMSE by Rate Group Frequency")
    plot_wall_time_comparison(runs_by_prefix, out_dir,
                              "rg_wall_time.png", "Wall Time by Rate Group Frequency")
    plot_dep_overlay(runs_by_prefix, out_dir,
                     "rg_dep_overlay.png", "Airbrake Deployment by Rate Group Frequency")
    plot_trajectory_overlay(runs_by_prefix, logs_dir, out_dir,
                            "rg_trajectory.png", "Trajectory by Rate Group Frequency")
    export_all_runs_csv(runs_by_prefix, nonsil_dep_baseline, out_dir)


def run_basic_compare(logs_dir, out_dir):
    """Original sil vs nonsil comparison using old filename style."""
    nonsil_runs = load_runs(logs_dir, "nonsil")
    sil_runs    = load_runs(logs_dir, "sil")

    if not nonsil_runs and not sil_runs:
        print("No runs found.")
        return

    runs_by_prefix = {}
    if nonsil_runs:
        runs_by_prefix["nonsil"] = nonsil_runs
    if sil_runs:
        runs_by_prefix["sil"] = sil_runs

    nonsil_dep_baseline = interpolate_dep(
        nonsil_runs[0]["dep_series"], T_GRID) if nonsil_runs else None
    nonsil_mean = np.mean([r["apogee_m"] for r in nonsil_runs]) if nonsil_runs else None

    for prefix, runs in runs_by_prefix.items():
        print_summary(prefix, runs, nonsil_dep_baseline)

    if nonsil_runs and sil_runs:
        plot_apogee_comparison(runs_by_prefix, nonsil_mean, out_dir,
                               "summary_apogee.png", "SIL vs Non-SIL Apogee")
        if nonsil_dep_baseline is not None:
            plot_dep_rmse_comparison(runs_by_prefix, nonsil_dep_baseline, out_dir,
                                     "summary_dep_rmse.png", "SIL vs Non-SIL DEP RMSE")
        plot_wall_time_comparison(runs_by_prefix, out_dir,
                                  "summary_wall_time.png", "SIL vs Non-SIL Wall Time")
        plot_dep_overlay(runs_by_prefix, out_dir,
                         "summary_dep_overlay.png", "Airbrake Deployment SIL vs Non-SIL")
        plot_trajectory_overlay(runs_by_prefix, logs_dir, out_dir,
                                "summary_trajectory.png", "Trajectory SIL vs Non-SIL")
        export_all_runs_csv(runs_by_prefix, nonsil_dep_baseline, out_dir)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RITL thesis analysis")
    parser.add_argument("--logs",   type=Path, default=LOGS_DIR_DEFAULT)
    parser.add_argument("--out",    type=Path, default=OUT_DIR_DEFAULT)
    parser.add_argument("--rocket", choices=["calisto", "cameos"], default="calisto")
    parser.add_argument("--rategroup-sweep", action="store_true",
                        help="Compare rate group frequencies")
    parser.add_argument("--arch-compare", action="store_true",
                        help="Compare all architectures")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"\nLogs: {args.logs.resolve()}")
    print(f"Out:  {args.out.resolve()}\n")

    if args.rategroup_sweep:
        run_rategroup_sweep(args.logs, args.out, args.rocket)
    elif args.arch_compare:
        run_arch_compare(args.logs, args.out, args.rocket)
    else:
        run_basic_compare(args.logs, args.out)

    print(f"\nDone. Results in: {args.out.resolve()}\n")


if __name__ == "__main__":
    main()
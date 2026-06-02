"""
RITL Experiment Analysis
========================
Analyses results from:
  - ritl_experiment           (nonsil, sil/hil lockstep/snapshot)
  - ritl_rategroup_Xhz_experiment  (rategroup frequency sweep: 1,5,10,25,50 Hz)

Usage:
    python analysis.py --experiments /path/to/experiments --out results/
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RE_APOGEE    = re.compile(r"APOGEE\s+([\d.]+)\s+([\d.]+)")
RE_DROGUE    = re.compile(r"DROGUE\s+([\d.]+)")
RE_MAIN      = re.compile(r"MAIN\s+([\d.]+)")
RE_WALL_TIME = re.compile(r"WALL_TIME\s+([\d.]+)")
RE_DEP       = re.compile(r"DEP\s+([\d.]+)\s+([\d.]+)")

COLORS = {
    "nonsil":        "#2196F3",
    "sil_lockstep":  "#F44336",
    "sil_snapshot":  "#FF9800",
    "hil_lockstep":  "#9C27B0",
    "hil_snapshot":  "#4CAF50",
}
RATEGROUP_CMAP = plt.cm.plasma

LABELS = {
    "nonsil":        "Non-SIL",
    "sil_lockstep":  "SIL Lockstep",
    "sil_snapshot":  "SIL Snapshot",
    "hil_lockstep":  "HIL Lockstep",
    "hil_snapshot":  "HIL Snapshot",
}

plt.rcParams.update({
    "figure.dpi":       150,
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "axes.grid":        True,
    "grid.alpha":       0.3,
    "grid.linestyle":   "--",
    "font.size":        11,
    "axes.titlesize":   13,
    "axes.labelsize":   11,
    "legend.fontsize":  10,
})


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def find_main_log(run_dir: Path) -> Path | None:
    """Return the main log file in a run dir, ignoring hil_fsw.log."""
    logs = [f for f in run_dir.glob("*.log") if f.name != "hil_fsw.log"]
    if not logs:
        return None
    return logs[0]


def parse_log(path: Path) -> dict | None:
    text = path.read_text(errors="replace")
    apogee = apogee_time = drogue = main = wall_time = None
    dep_series = []

    for line in text.splitlines():
        if apogee is None:
            m = RE_APOGEE.search(line)
            if m:
                apogee      = float(m.group(1))
                apogee_time = float(m.group(2))
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

    if None in (apogee, drogue, main):
        return None

    return {
        "apogee_m":    apogee,
        "apogee_time": apogee_time,
        "drogue_s":    drogue,
        "main_s":      main,
        "wall_time_s": wall_time,
        "dep_series":  dep_series,
    }


def load_experiment(exp_dir: Path) -> pd.DataFrame:
    """Load run_table.csv and merge with parsed log data."""
    csv_path = exp_dir / "run_table.csv"
    if not csv_path.exists():
        print(f"  WARNING: no run_table.csv in {exp_dir}")
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    df = df[df["success"] == True].copy()

    rows = []
    for _, row in df.iterrows():
        run_id  = row["__run_id"]
        run_dir = exp_dir / run_id
        if not run_dir.exists():
            continue
        log = find_main_log(run_dir)
        if log is None:
            continue
        parsed = parse_log(log)
        if parsed is None:
            print(f"  WARNING: incomplete log skipped: {log}")
            continue

        merged = row.to_dict()
        merged.update(parsed)
        rows.append(merged)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    print(f"  Loaded {len(result)} valid runs from {exp_dir.name}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def summary_table(df: pd.DataFrame, group_col: str, metrics: list[str]) -> pd.DataFrame:
    rows = []
    for grp, gdf in df.groupby(group_col):
        for m in metrics:
            if m not in gdf.columns:
                continue
            vals = gdf[m].dropna()
            rows.append({
                group_col: grp,
                "metric":  m,
                "n":       len(vals),
                "mean":    vals.mean(),
                "std":     vals.std(ddof=1),
                "min":     vals.min(),
                "max":     vals.max(),
            })
    return pd.DataFrame(rows)


def welch_ttest(df: pd.DataFrame, group_col: str, baseline: str, metric: str) -> pd.DataFrame:
    base_vals = df[df[group_col] == baseline][metric].dropna().values
    rows = []
    for grp, gdf in df.groupby(group_col):
        if grp == baseline:
            continue
        vals = gdf[metric].dropna().values
        t, p = stats.ttest_ind(base_vals, vals, equal_var=False)
        rows.append({
            "comparison": f"{baseline} vs {grp}",
            "t":          round(t, 4),
            "p":          round(p, 4),
            "significant": p < 0.05,
        })
    return pd.DataFrame(rows)


def interpolate_dep(dep_series: list, t_grid: np.ndarray) -> np.ndarray:
    if not dep_series:
        return np.zeros_like(t_grid)
    ts = np.array([d[0] for d in dep_series])
    vs = np.array([d[1] for d in dep_series])
    return np.interp(t_grid, ts, vs, left=0.0, right=0.0)


def dep_mean_band(runs_dep: list, t_grid: np.ndarray):
    interps = np.array([interpolate_dep(d, t_grid) for d in runs_dep])
    return interps.mean(axis=0), interps.std(axis=0, ddof=1)


# ─────────────────────────────────────────────────────────────────────────────
# Part 1 — Main experiment plots
# ─────────────────────────────────────────────────────────────────────────────

MODE_ORDER = ["nonsil", "sil_lockstep", "sil_snapshot", "hil_lockstep", "hil_snapshot"]


def plot_apogee_bars(df: pd.DataFrame, baseline_mean: float, out_dir: Path):
    fig, ax = plt.subplots(figsize=(10, 5))
    modes   = [m for m in MODE_ORDER if m in df["mode"].values]
    means   = [df[df["mode"] == m]["apogee_m"].mean() for m in modes]
    stds    = [df[df["mode"] == m]["apogee_m"].std(ddof=1) for m in modes]
    colors  = [COLORS.get(m, "#888") for m in modes]
    xlabels = [LABELS.get(m, m) for m in modes]

    ax.bar(xlabels, means, yerr=stds, color=colors, alpha=0.85,
           capsize=6, width=0.55, ecolor="black", error_kw={"linewidth": 1.2})

    for i, m in enumerate(modes):
        vals = df[df["mode"] == m]["apogee_m"].dropna().values
        ax.scatter([i] * len(vals), vals, color="black", s=12, zorder=5, alpha=0.4)

    ax.axhline(baseline_mean, color=COLORS["nonsil"], linestyle="--",
               linewidth=1.5, label=f"Non-SIL baseline ({baseline_mean:.1f} m)")

    all_vals = df[df["mode"].isin(modes)]["apogee_m"].dropna()
    ax.set_ylim(all_vals.min() - 2, all_vals.max() + 2)
    ax.set_ylabel("Apogee AGL (m)")
    ax.set_title("Mean Apogee per Coupling Mode (± 1 std dev)")
    ax.legend()
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    path = out_dir / "apogee_bars.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_wall_time_bars(df: pd.DataFrame, out_dir: Path):
    fig, ax = plt.subplots(figsize=(10, 5))
    modes   = [m for m in MODE_ORDER if m in df["mode"].values]
    means   = [df[df["mode"] == m]["wall_time_s"].mean() for m in modes]
    stds    = [df[df["mode"] == m]["wall_time_s"].std(ddof=1) for m in modes]
    colors  = [COLORS.get(m, "#888") for m in modes]
    xlabels = [LABELS.get(m, m) for m in modes]

    ax.bar(xlabels, means, yerr=stds, color=colors, alpha=0.85,
           capsize=6, width=0.55, ecolor="black", error_kw={"linewidth": 1.2})

    ax.set_ylabel("Wall time (s)")
    ax.set_title("Mean Simulation Wall Time per Mode (± 1 std dev)")
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    path = out_dir / "wall_time_bars.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_wall_time_violin(df: pd.DataFrame, out_dir: Path):
    """
    NEW: Violin + strip plot of wall times per mode.
    Reveals distribution shape and outliers hidden by bar+errorbar plots.
    """
    modes   = [m for m in MODE_ORDER if m in df["mode"].values]
    xlabels = [LABELS.get(m, m) for m in modes]
    data    = [df[df["mode"] == m]["wall_time_s"].dropna().values for m in modes]
    colors  = [COLORS.get(m, "#888") for m in modes]

    fig, ax = plt.subplots(figsize=(10, 5))

    parts = ax.violinplot(data, positions=range(len(modes)),
                          showmedians=True, showextrema=True, widths=0.6)

    # Colour each violin body
    for pc, color in zip(parts["bodies"], colors):
        pc.set_facecolor(color)
        pc.set_alpha(0.6)
    for part in ("cmedians", "cmins", "cmaxes", "cbars"):
        parts[part].set_color("black")
        parts[part].set_linewidth(1.2)

    # Overlay individual points (jittered)
    rng = np.random.default_rng(42)
    for i, (vals, color) in enumerate(zip(data, colors)):
        jitter = rng.uniform(-0.08, 0.08, size=len(vals))
        ax.scatter(i + jitter, vals, color=color, s=25, zorder=5,
                   edgecolors="black", linewidths=0.4, alpha=0.8)

    # Annotate outliers (> mean + 2*std)
    for i, (vals, m) in enumerate(zip(data, modes)):
        threshold = vals.mean() + 2 * vals.std()
        for v in vals:
            if v > threshold:
                ax.annotate(f"{v:.1f} s", xy=(i, v),
                            xytext=(8, 2), textcoords="offset points",
                            fontsize=8, color="red",
                            arrowprops=dict(arrowstyle="-", color="red", lw=0.8))

    ax.set_xticks(range(len(modes)))
    ax.set_xticklabels(xlabels, rotation=15, ha="right")
    ax.set_ylabel("Wall time (s)")
    ax.set_title("Wall Time Distribution per Coupling Mode")
    plt.tight_layout()
    path = out_dir / "wall_time_violin.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_apogee_error_bars(df: pd.DataFrame, baseline_mean: float, out_dir: Path):
    fig, ax = plt.subplots(figsize=(10, 5))
    modes = [m for m in MODE_ORDER if m in df["mode"].values and m != "nonsil"]
    errors = [df[df["mode"] == m]["apogee_m"].mean() - baseline_mean for m in modes]
    colors = [COLORS.get(m, "#888") for m in modes]
    xlabels = [LABELS.get(m, m) for m in modes]

    ax.bar(xlabels, errors, color=colors, alpha=0.85, width=0.55)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_ylabel("Apogee error vs Non-SIL (m)")
    ax.set_title("Apogee Error Relative to Non-SIL Baseline")
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    path = out_dir / "apogee_error_bars.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_parachute_timing(df: pd.DataFrame, out_dir: Path):
    """
    NEW: Grouped bar chart of drogue and main deployment times per mode.
    Highlights the ~0.5 s drogue delay introduced by SIL/HIL coupling.
    """
    modes   = [m for m in MODE_ORDER if m in df["mode"].values]
    xlabels = [LABELS.get(m, m) for m in modes]
    n       = len(modes)
    x       = np.arange(n)
    width   = 0.35

    drogue_means = [df[df["mode"] == m]["drogue_s"].mean() for m in modes]
    drogue_stds  = [df[df["mode"] == m]["drogue_s"].std(ddof=1) for m in modes]
    main_means   = [df[df["mode"] == m]["main_s"].mean() for m in modes]
    main_stds    = [df[df["mode"] == m]["main_s"].std(ddof=1) for m in modes]

    fig, ax = plt.subplots(figsize=(11, 5))

    bars1 = ax.bar(x - width / 2, drogue_means, width, yerr=drogue_stds,
                   color=[COLORS.get(m, "#888") for m in modes],
                   alpha=0.85, capsize=5, ecolor="black",
                   error_kw={"linewidth": 1.1}, label="Drogue deployment (s)")

    bars2 = ax.bar(x + width / 2, main_means, width, yerr=main_stds,
                   color=[COLORS.get(m, "#888") for m in modes],
                   alpha=0.40, capsize=5, ecolor="black",
                   error_kw={"linewidth": 1.1}, label="Main deployment (s)",
                   hatch="//")

    # Annotate drogue bars with mean value
    for bar, mean in zip(bars1, drogue_means):
        ax.text(bar.get_x() + bar.get_width() / 2, mean + 0.05,
                f"{mean:.2f}", ha="center", va="bottom", fontsize=8)

    # Reference lines for Non-SIL values
    nonsil_drogue = df[df["mode"] == "nonsil"]["drogue_s"].mean()
    nonsil_main   = df[df["mode"] == "nonsil"]["main_s"].mean()
    ax.axhline(nonsil_drogue, color=COLORS["nonsil"], linestyle="--",
               linewidth=1.2, alpha=0.7, label=f"Non-SIL drogue ({nonsil_drogue:.2f} s)")
    ax.axhline(nonsil_main, color=COLORS["nonsil"], linestyle=":",
               linewidth=1.2, alpha=0.7, label=f"Non-SIL main ({nonsil_main:.2f} s)")

    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, rotation=15, ha="right")
    ax.set_ylabel("Deployment time (s)")
    ax.set_title("Parachute Deployment Timing per Coupling Mode (± 1 std dev)")
    ax.legend(fontsize=9)

    # Zoom y-axis: deployment events span ~24–45 s
    all_times = drogue_means + main_means
    ax.set_ylim(min(all_times) - 1.5, max(all_times) + 1.5)

    plt.tight_layout()
    path = out_dir / "parachute_timing.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")

    # Also save a drogue-only zoomed plot (more readable for that signal)
    fig, ax = plt.subplots(figsize=(10, 4))
    for i, (m, mean, std) in enumerate(zip(modes, drogue_means, drogue_stds)):
        color = COLORS.get(m, "#888")
        vals  = df[df["mode"] == m]["drogue_s"].dropna().values
        ax.bar(i, mean, yerr=std, color=color, alpha=0.85, width=0.55,
               capsize=5, ecolor="black", error_kw={"linewidth": 1.1})
        ax.scatter([i] * len(vals), vals, color="black", s=18, zorder=5, alpha=0.5)
        ax.text(i, mean + std + 0.003, f"{mean:.3f} s",
                ha="center", va="bottom", fontsize=8)

    ax.axhline(nonsil_drogue, color=COLORS["nonsil"], linestyle="--",
               linewidth=1.4, label=f"Non-SIL baseline ({nonsil_drogue:.3f} s)")
    ax.set_xticks(range(n))
    ax.set_xticklabels(xlabels, rotation=15, ha="right")
    ax.set_ylabel("Drogue deployment time (s)")
    ax.set_title("Drogue Deployment Time per Coupling Mode (± 1 std dev)")
    ax.legend()
    drogue_all = df["drogue_s"].dropna()
    ax.set_ylim(drogue_all.min() - 0.3, drogue_all.max() + 0.2)
    plt.tight_layout()
    path = out_dir / "drogue_timing_zoomed.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_dep_bands(df: pd.DataFrame, out_dir: Path):
    all_ts = []
    for deps in df["dep_series"]:
        if deps:
            all_ts.extend([d[0] for d in deps])
    if not all_ts:
        print("  No DEP data for main experiment.")
        return

    t_grid = np.linspace(min(all_ts), max(all_ts), 500)

    mode_curves = {}
    for mode in MODE_ORDER:
        sub = df[df["mode"] == mode]
        if sub.empty:
            continue
        deps = [r for r in sub["dep_series"] if r]
        if not deps:
            continue
        mean, std = dep_mean_band(deps, t_grid)
        mode_curves[mode] = (mean, std)

    # Plot 1: full deployment curve
    fig, ax = plt.subplots(figsize=(12, 5))
    for mode, (mean, std) in mode_curves.items():
        color = COLORS.get(mode, "#888")
        ax.plot(t_grid, mean, color=color, linewidth=2, label=LABELS.get(mode, mode))
        ax.fill_between(t_grid, mean - std, mean + std, color=color, alpha=0.15)

    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Airbrake deployment level")
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("Airbrake Deployment Level — Mean ± 1 Std Dev per Mode")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "dep_bands.png")
    plt.close()
    print(f"  Saved: {out_dir / 'dep_bands.png'}")

    # Plot 2: full + zoomed side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle("Airbrake Deployment Level — Mean ± 1 Std Dev per Mode", fontweight="bold")

    for mode, (mean, std) in mode_curves.items():
        color = COLORS.get(mode, "#888")
        label = LABELS.get(mode, mode)
        for ax in (ax1, ax2):
            ax.plot(t_grid, mean, color=color, linewidth=2, label=label)
            ax.fill_between(t_grid, mean - std, mean + std, color=color, alpha=0.15)

    ax1.set_xlabel("Simulation time (s)")
    ax1.set_ylabel("Airbrake deployment level")
    ax1.set_ylim(-0.05, 1.1)
    ax1.set_title("Full flight")
    ax1.legend(fontsize=9)

    ax2.set_xlim(6, 15)
    ax2.set_ylim(-0.02, 0.25)
    ax2.set_xlabel("Simulation time (s)")
    ax2.set_ylabel("Airbrake deployment level")
    ax2.set_title("Zoomed: t = 6–15 s (divergence region)")
    ax2.legend(fontsize=9)

    plt.tight_layout()
    plt.savefig(out_dir / "dep_bands_zoomed.png")
    plt.close()
    print(f"  Saved: {out_dir / 'dep_bands_zoomed.png'}")

    # Plot 3: difference from nonsil baseline
    if "nonsil" not in mode_curves:
        return

    baseline_dep, _ = mode_curves["nonsil"]
    fig, ax = plt.subplots(figsize=(12, 5))

    for mode, (mean, std) in mode_curves.items():
        if mode == "nonsil":
            continue
        diff = mean - baseline_dep
        color = COLORS.get(mode, "#888")
        ax.plot(t_grid, diff, color=color, linewidth=2, label=LABELS.get(mode, mode))
        ax.fill_between(t_grid, diff - std, diff + std, color=color, alpha=0.12)

    ax.axhline(0, color="black", linewidth=1, linestyle="--", alpha=0.5)
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Deployment level difference vs Non-SIL")
    ax.set_title("Airbrake Deployment Difference from Non-SIL Baseline")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "dep_diff_from_nonsil.png")
    plt.close()
    print(f"  Saved: {out_dir / 'dep_diff_from_nonsil.png'}")


def plot_sil_hil_scatter(df: pd.DataFrame, out_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("SIL vs HIL Apogee Agreement per Repetition", fontsize=13, fontweight="bold")

    pairs = [
        ("sil_lockstep", "hil_lockstep", "Lockstep", axes[0]),
        ("sil_snapshot",  "hil_snapshot",  "Snapshot",  axes[1]),
    ]

    for sil_mode, hil_mode, title, ax in pairs:
        sil_df = df[df["mode"] == sil_mode].copy()
        hil_df = df[df["mode"] == hil_mode].copy()

        sil_df["rep"] = sil_df["__run_id"].str.extract(r"repetition_(\d+)").astype(int)
        hil_df["rep"] = hil_df["__run_id"].str.extract(r"repetition_(\d+)").astype(int)
        merged = pd.merge(sil_df[["rep", "apogee_m"]], hil_df[["rep", "apogee_m"]],
                          on="rep", suffixes=("_sil", "_hil"))

        if merged.empty:
            ax.set_title(f"{title} — no matched pairs")
            continue

        ax.scatter(merged["apogee_m_sil"], merged["apogee_m_hil"],
                   color=COLORS.get(sil_mode, "#888"), s=60, zorder=5)

        all_vals = pd.concat([merged["apogee_m_sil"], merged["apogee_m_hil"]])
        lim = [all_vals.min() - 2, all_vals.max() + 2]
        ax.plot(lim, lim, "k--", linewidth=1, alpha=0.5, label="Identity")
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel("SIL Apogee (m)")
        ax.set_ylabel("HIL Apogee (m)")
        ax.set_title(title)
        ax.legend()

        diff = merged["apogee_m_sil"] - merged["apogee_m_hil"]
        ax.text(0.05, 0.95, f"Mean diff: {diff.mean():.3f} m\nStd: {diff.std():.3f} m",
                transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7))

    plt.tight_layout()
    plt.savefig(out_dir / "sil_hil_scatter.png")
    plt.close()
    print(f"  Saved: {out_dir / 'sil_hil_scatter.png'}")


def sil_hil_diff_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sil_mode, hil_mode, label in [
        ("sil_lockstep", "hil_lockstep", "Lockstep"),
        ("sil_snapshot",  "hil_snapshot",  "Snapshot"),
    ]:
        sil_df = df[df["mode"] == sil_mode].copy()
        hil_df = df[df["mode"] == hil_mode].copy()
        sil_df["rep"] = sil_df["__run_id"].str.extract(r"repetition_(\d+)").astype(int)
        hil_df["rep"] = hil_df["__run_id"].str.extract(r"repetition_(\d+)").astype(int)
        merged = pd.merge(sil_df[["rep", "apogee_m"]], hil_df[["rep", "apogee_m"]],
                          on="rep", suffixes=("_sil", "_hil"))
        if merged.empty:
            continue
        diff = merged["apogee_m_sil"] - merged["apogee_m_hil"]
        rows.append({
            "pair":      label,
            "n_pairs":   len(diff),
            "mean_diff": round(diff.mean(), 4),
            "std_diff":  round(diff.std(ddof=1), 4),
            "max_diff":  round(diff.abs().max(), 4),
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Part 2 — Rategroup frequency sweep
# ─────────────────────────────────────────────────────────────────────────────

def plot_rategroup_apogee(rg_data: dict, baseline_mean: float, out_dir: Path):
    freqs  = sorted(rg_data.keys())

    fig, ax = plt.subplots(figsize=(9, 5))
    means, stds = [], []
    for hz in freqs:
        vals = rg_data[hz]["apogee_m"].dropna()
        means.append(vals.mean())
        stds.append(vals.std(ddof=1))

    ax.errorbar(freqs, means, yerr=stds, fmt="o-", color="#E91E63",
                capsize=6, linewidth=2, markersize=7, label="Rategroup (SIL)")
    ax.axhline(baseline_mean, color=COLORS["nonsil"], linestyle="--",
               linewidth=1.5, label=f"Non-SIL baseline ({baseline_mean:.1f} m)")

    ax.set_xlabel("Rate group frequency (Hz)")
    ax.set_ylabel("Apogee AGL (m)")
    ax.set_title("Apogee vs FSW Rate Group Frequency")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax.set_xticks(freqs)
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "rategroup_apogee_vs_freq.png")
    plt.close()
    print(f"  Saved: {out_dir / 'rategroup_apogee_vs_freq.png'}")


def plot_rategroup_apogee_with_fit(rg_data: dict, baseline_mean: float, out_dir: Path):
    """
    NEW: Apogee error vs frequency with power-law curve fit and knee annotation.
    Answers: "what is the minimum practical rate group frequency?"
    """
    freqs = np.array(sorted(rg_data.keys()), dtype=float)
    means = np.array([rg_data[int(hz)]["apogee_m"].dropna().mean() for hz in freqs])
    stds  = np.array([rg_data[int(hz)]["apogee_m"].dropna().std(ddof=1) for hz in freqs])
    errors = means - baseline_mean

    # Fit: error(f) = a / f^b + c  (power law with floor)
    def power_floor(f, a, b, c):
        return a / f**b + c

    try:
        popt, pcov = curve_fit(power_floor, freqs, errors,
                               p0=[300, 0.7, errors[-1]], maxfev=10000)
        fit_ok = True
    except RuntimeError:
        fit_ok = False

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Rate Group Frequency vs Apogee Error (relative to Non-SIL baseline)",
                 fontweight="bold")

    for ax, use_log in zip(axes, [False, True]):
        ax.errorbar(freqs, errors, yerr=stds, fmt="o", color="#E91E63",
                    capsize=6, markersize=8, zorder=5, label="Measured error")

        if fit_ok:
            f_fine = np.linspace(0.8, 60, 500) if not use_log else np.logspace(
                np.log10(0.8), np.log10(60), 500)
            ax.plot(f_fine, power_floor(f_fine, *popt), color="#FF6F00",
                    linewidth=2, linestyle="--",
                    label=f"Fit: {popt[0]:.0f}/f^{popt[1]:.2f} + {popt[2]:.1f}")

            # Knee: where error crosses 10 m and 5 m above baseline floor
            f_test = np.linspace(0.5, 100, 50000)
            pred   = power_floor(f_test, *popt)
            for thresh, ls, col in [(10, ":", "#1976D2"), (5, "-.", "#388E3C")]:
                idx = np.argmax(pred <= thresh)
                if pred[idx] <= thresh:
                    knee_f = f_test[idx]
                    ax.axvline(knee_f, color=col, linestyle=ls, linewidth=1.4,
                               label=f"<{thresh} m error at {knee_f:.0f} Hz")
                    ax.axhline(thresh, color=col, linestyle=ls, linewidth=0.8, alpha=0.5)

        ax.axhline(0, color="black", linewidth=1, linestyle="--", alpha=0.4,
                   label="Baseline floor (0 m)")
        ax.set_xlabel("Rate group frequency (Hz)")
        ax.set_ylabel("Apogee error vs Non-SIL (m)")

        if use_log:
            ax.set_xscale("log")
            ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
            ax.set_xticks(list(freqs) + [60])
            ax.set_title("Log-scale frequency axis")
        else:
            ax.set_title("Linear frequency axis")

        ax.legend(fontsize=9)
        ax.set_ylim(-5, errors.max() + 20)

    plt.tight_layout()
    path = out_dir / "rategroup_apogee_error_fit.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")

    # Export fit parameters
    if fit_ok:
        fit_path = out_dir / "rategroup_apogee_fit_params.csv"
        pd.DataFrame([{
            "a": round(popt[0], 3),
            "b": round(popt[1], 4),
            "c": round(popt[2], 3),
            "model": "error = a / f^b + c",
        }]).to_csv(fit_path, index=False)
        print(f"  Saved: {fit_path}")


def plot_rategroup_wall_time(rg_data: dict, out_dir: Path):
    freqs = sorted(rg_data.keys())
    means, stds = [], []
    for hz in freqs:
        vals = rg_data[hz]["wall_time_s"].dropna()
        means.append(vals.mean())
        stds.append(vals.std(ddof=1))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.errorbar(freqs, means, yerr=stds, fmt="s-", color="#9C27B0",
                capsize=6, linewidth=2, markersize=7)
    ax.set_xlabel("Rate group frequency (Hz)")
    ax.set_ylabel("Wall time (s)")
    ax.set_title("Simulation Wall Time vs FSW Rate Group Frequency")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax.set_xticks(freqs)
    plt.tight_layout()
    plt.savefig(out_dir / "rategroup_walltime_vs_freq.png")
    plt.close()
    print(f"  Saved: {out_dir / 'rategroup_walltime_vs_freq.png'}")


def plot_rategroup_wall_time_violin(rg_data: dict, out_dir: Path):
    """
    NEW: Violin plot of wall time per rate group frequency.
    Exposes the large outlier at 5 Hz hidden by the error-bar plot.
    """
    freqs  = sorted(rg_data.keys())
    data   = [rg_data[hz]["wall_time_s"].dropna().values for hz in freqs]
    colors = [plt.cm.plasma(i / max(len(freqs) - 1, 1)) for i in range(len(freqs))]

    fig, ax = plt.subplots(figsize=(10, 5))

    parts = ax.violinplot(data, positions=range(len(freqs)),
                          showmedians=True, showextrema=True, widths=0.6)

    for pc, color in zip(parts["bodies"], colors):
        pc.set_facecolor(color)
        pc.set_alpha(0.6)
    for part in ("cmedians", "cmins", "cmaxes", "cbars"):
        parts[part].set_color("black")
        parts[part].set_linewidth(1.2)

    rng = np.random.default_rng(42)
    for i, (vals, color) in enumerate(zip(data, colors)):
        jitter = rng.uniform(-0.08, 0.08, size=len(vals))
        ax.scatter(i + jitter, vals, color=color, s=25, zorder=5,
                   edgecolors="black", linewidths=0.4, alpha=0.85)

    # Annotate outliers (> mean + 2*std)
    for i, (vals, hz) in enumerate(zip(data, freqs)):
        threshold = vals.mean() + 2 * vals.std()
        for v in vals:
            if v > threshold:
                ax.annotate(f"{v:.1f} s\n(outlier)", xy=(i, v),
                            xytext=(12, 0), textcoords="offset points",
                            fontsize=8, color="red", va="center",
                            arrowprops=dict(arrowstyle="->", color="red", lw=0.8))

    ax.set_xticks(range(len(freqs)))
    ax.set_xticklabels([f"{hz} Hz" for hz in freqs])
    ax.set_ylabel("Wall time (s)")
    ax.set_title("Wall Time Distribution per Rate Group Frequency\n"
                 "(outliers annotated; data points jittered for visibility)")
    plt.tight_layout()
    path = out_dir / "rategroup_walltime_violin.png"
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_rategroup_dep_bands(rg_data: dict, out_dir: Path):
    all_ts = []
    for df in rg_data.values():
        for deps in df["dep_series"]:
            if deps:
                all_ts.extend([d[0] for d in deps])
    if not all_ts:
        print("  No DEP data for rategroup experiment.")
        return

    t_grid = np.linspace(min(all_ts), max(all_ts), 500)
    freqs  = sorted(rg_data.keys())
    colors = [RATEGROUP_CMAP(i / max(len(freqs) - 1, 1)) for i in range(len(freqs))]

    fig, ax = plt.subplots(figsize=(12, 5))
    for hz, color in zip(freqs, colors):
        deps = [r for r in rg_data[hz]["dep_series"] if r]
        if not deps:
            continue
        mean, std = dep_mean_band(deps, t_grid)
        ax.plot(t_grid, mean, color=color, linewidth=2, label=f"{hz} Hz")
        ax.fill_between(t_grid, mean - std, mean + std, color=color, alpha=0.12)

    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Airbrake deployment level")
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("Airbrake Deployment — Mean ± 1 Std Dev per Rate Group Frequency")
    ax.legend(title="Frequency")
    plt.tight_layout()
    plt.savefig(out_dir / "rategroup_dep_bands.png")
    plt.close()
    print(f"  Saved: {out_dir / 'rategroup_dep_bands.png'}")

    fig, ax = plt.subplots(figsize=(12, 5))
    for hz, color in zip(freqs, colors):
        deps = [r for r in rg_data[hz]["dep_series"] if r]
        if not deps:
            continue
        mean, std = dep_mean_band(deps, t_grid)
        ax.plot(t_grid, mean, color=color, linewidth=2, label=f"{hz} Hz")
        ax.fill_between(t_grid, mean - std, mean + std, color=color, alpha=0.12)

    ax.set_xlim(3, 22)
    ax.set_ylim(-0.05, 1.1)
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Airbrake deployment level")
    ax.set_title("Airbrake Deployment — Zoomed to Active Window (t = 3–22 s)")
    ax.legend(title="Frequency")
    plt.tight_layout()
    plt.savefig(out_dir / "rategroup_dep_bands_zoomed.png")
    plt.close()
    print(f"  Saved: {out_dir / 'rategroup_dep_bands_zoomed.png'}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RITL experiment analysis")
    parser.add_argument("--experiments", type=Path,
                        default=Path(__file__).parent / "experiments",
                        help="Path to experiments directory")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).parent / "results",
                        help="Output directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    # ── Load main experiment ──────────────────────────────────────────────────
    print("\n── Loading main experiment ──────────────────────────────")
    main_exp_dir = args.experiments / "ritl_experiment"
    main_df = load_experiment(main_exp_dir)

    if main_df.empty:
        print("ERROR: no data loaded from ritl_experiment. Check path.")
        sys.exit(1)

    baseline_mean = main_df[main_df["mode"] == "nonsil"]["apogee_m"].mean()
    print(f"  Non-SIL baseline apogee: {baseline_mean:.4f} m")

    # ── Load rategroup experiments ────────────────────────────────────────────
    print("\n── Loading rategroup experiments ────────────────────────")
    rg_freqs = [1, 5, 10, 25, 50]
    rg_data  = {}
    for hz in rg_freqs:
        exp_dir = args.experiments / f"ritl_rategroup_{hz}hz_experiment"
        if not exp_dir.exists():
            print(f"  Skipping {hz}Hz — directory not found")
            continue
        df = load_experiment(exp_dir)
        if not df.empty:
            rg_data[hz] = df

    # ── Summary stats ─────────────────────────────────────────────────────────
    print("\n── Summary Statistics (main experiment) ─────────────────")
    metrics = ["apogee_m", "wall_time_s", "drogue_s", "main_s"]
    stats_df = summary_table(main_df, "mode", metrics)
    print(stats_df.to_string(index=False))
    stats_df.to_csv(args.out / "summary_stats.csv", index=False)
    print(f"\n  Saved: {args.out / 'summary_stats.csv'}")

    # ── T-tests ───────────────────────────────────────────────────────────────
    print("\n── Welch T-Tests vs Non-SIL baseline (apogee) ──────────")
    ttest_df = welch_ttest(main_df, "mode", "nonsil", "apogee_m")
    print(ttest_df.to_string(index=False))
    ttest_df.to_csv(args.out / "ttest_apogee.csv", index=False)
    print(f"\n  Saved: {args.out / 'ttest_apogee.csv'}")

    print("\n── SIL vs HIL Agreement ─────────────────────────────────")
    diff_df = sil_hil_diff_table(main_df)
    print(diff_df.to_string(index=False))
    diff_df.to_csv(args.out / "sil_hil_diff.csv", index=False)
    print(f"\n  Saved: {args.out / 'sil_hil_diff.csv'}")

    if rg_data:
        print("Rategroup Summary")
        rg_rows = []
        for hz, df in sorted(rg_data.items()):
            for m in ["apogee_m", "wall_time_s"]:
                vals = df[m].dropna()
                rg_rows.append({
                    "freq_hz": hz,
                    "metric":  m,
                    "n":       len(vals),
                    "mean":    round(vals.mean(), 4),
                    "std":     round(vals.std(ddof=1), 4),
                    "min":     round(vals.min(), 4),
                    "max":     round(vals.max(), 4),
                })
        rg_stats_df = pd.DataFrame(rg_rows)
        print(rg_stats_df.to_string(index=False))
        rg_stats_df.to_csv(args.out / "rategroup_stats.csv", index=False)
        print(f"\n  Saved: {args.out / 'rategroup_stats.csv'}")

    # ── Plots ─────────────────────────────────────────────────────────────────
    print("\n── Generating plots ─────────────────────────────────────")

    # Original plots
    plot_apogee_bars(main_df, baseline_mean, args.out)
    plot_wall_time_bars(main_df, args.out)
    plot_apogee_error_bars(main_df, baseline_mean, args.out)
    plot_dep_bands(main_df, args.out)
    plot_sil_hil_scatter(main_df, args.out)

    # NEW plots
    plot_wall_time_violin(main_df, args.out)
    plot_parachute_timing(main_df, args.out)

    if rg_data:
        plot_rategroup_apogee(rg_data, baseline_mean, args.out)
        plot_rategroup_wall_time(rg_data, args.out)
        plot_rategroup_dep_bands(rg_data, args.out)
        # NEW plots
        plot_rategroup_apogee_with_fit(rg_data, baseline_mean, args.out)
        plot_rategroup_wall_time_violin(rg_data, args.out)

    print(f"\n── Done. All results saved to: {args.out.resolve()} ──\n")


if __name__ == "__main__":
    main()
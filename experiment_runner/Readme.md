# RITL Experiment Runner — How to Run

## Overview

Two RunnerConfigs cover all experiments:

- **`RunnerConfig.py`** — all non-rategroup architectures (lockstep, sensordriven, nonsil). Runs fully unattended.
- **`RunnerConfig_rategroup.py`** — rategroup architecture at a specific frequency. Run once per frequency.

Results go to separate folders under `experiments/` and share the same CSV column structure 

---

## Architectures & Binaries

| Architecture | FSW binary | RunnerConfig |
|---|---|---|
| Nonsil (baseline) | none needed | `RunnerConfig.py` |
| Control Lockstep | sensor driven (default) | `RunnerConfig.py` |
| Sensor Driven | sensor driven (default) | `RunnerConfig.py` |
| Rate Group 1hz | rategroup branch, 1hz build | `RunnerConfig_rategroup.py` |
| Rate Group 5hz | rategroup branch, 5hz build | `RunnerConfig_rategroup.py` |
| Rate Group 10hz | rategroup branch, 10hz build | `RunnerConfig_rategroup.py` |
| Rate Group 25hz | rategroup branch, 25hz build | `RunnerConfig_rategroup.py` |
| Rate Group 50hz | rategroup branch, 50hz build | `RunnerConfig_rategroup.py` |

---

## Step 1 — Run the main experiment (unattended)

### Build the default FSW binary

```bash
git checkout main
fprime-util build
```

##### For HIL, copy to Pi:
```bash
scp <binary_path> pi@10.42.0.142:/home/pi/RitlFsw_SilDeployment
```

### Choose modes in RunnerConfig.py

Edit the `mode_factor` list to include the modes you want:

```python
mode_factor = FactorModel("mode", [
    "nonsil",
    "sil_lockstep",
    "sil_nolockstep",
    "hil_lockstep",   # remove if Pi not connected
    "hil_nolockstep", # remove if Pi not connected
])
```

### Run it
from experiment runner repo

```bash
python experiment-runner/ ../rocket_in_the_loop/experiments/RunnerConfig.py
```

Results saved to `experiments/ritl_experiment/run_table.csv`.

---

## Step 2 — Run rategroup experiments (once per frequency)

For each frequency (10, 25, 50, 100hz):

### 1. Set the frequency in RunnerConfig_rategroup.py

```python
RATEGROUP_HZ = 10   # change to 25, 50, or 100
```

### 2. Build the FSW binary at that frequency

```bash
git checkout rategroup
# set frequency in FSW source
fprime-util build
```

#### For HIL, copy to Pi:

```bash
scp <binary_path> pi@10.42.0.142:/home/pi/RitlFsw_SilDeployment
```

### 3. Run it

```bash
python experiment-runner/ ../rocket_in_the_loop/experiments/RunnerConfig_rategroup.py
```

The runner will prompt you once at the start to confirm the binary is ready, then run all 10 reps unattended.

Results saved to `experiments/ritl_rategroup_10hz_experiment/run_table.csv`.

Repeat for each frequency — each gets its own folder.

---

## Output Structure

```
experiments/
  ritl_experiment/
    run_table.csv          ← nonsil, lockstep, nolockstep, sensordriven results
    run_0_repetition_0/
      sil_lockstep_cameos.log
      sil_lockstep_cameos_trajectory.csv
      ...

  ritl_rategroup_10hz_experiment/
    run_table.csv          ← rategroup sil + hil results at 10hz
    ...

  ritl_rategroup_25hz_experiment/
    run_table.csv
    ...
```

All CSVs share the same columns: `mode, apogee_m, apogee_time_s, drogue_s, main_s, wall_time_s, success`.

---

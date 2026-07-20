# RITL Experiment Runner — How to Run

Built on the [experiment-runner](https://github.com/S2-group/experiment-runner) framework. Each `RunnerConfig_*.py` in this directory is a standalone experiment: it patches `Ritl/config.yaml`, starts/stops the FSW (SIL via `fprime-gds`, HIL via SSH to the Pi), runs the sim through `docker compose`, and parses the resulting log into `experiments/<name>/run_table.csv`.

Setup:

```bash
git clone https://github.com/S2-group/experiment-runner
cd experiment-runner
```

Run any config from this directory:

```bash
cd experiment_runner
python -m experiment_runner RunnerConfig_<name>.py
```

For any `hil_*` mode, the FSW binary must already be running/deployed on the Pi (`pi@10.42.0.142`) before you start the run — the runner SSHs in to kill/start it but doesn't build or copy the binary.

---

## Runner configs

| File | Experiment | Modes | Notes |
|---|---|---|---|
| `RunnerConfig_coupling_strategy_comparison.py` | Main comparison across all architectures | `nonsil`, `sil_lockstep`, `sil_snapshot`, `hil_lockstep`, `hil_snapshot` | 10 reps/mode. The general-purpose baseline experiment. |
| `RunnerConfig_fault_injection.py` | Barometer freeze fault injection | `sil_snapshot`, `hil_snapshot` | Freezes the baro reading at `BARO_FREEZE_AT` (10s) via `fault_injection` in `config.yaml`, to see how the FSW handles a stale sensor. |
| `RunnerConfig_rategroup_sweep.py` | Rate-group architecture at a fixed frequency | `sil_rategroup`, `hil_rategroup` | Uses the time-triggered rategroup FSW build, not the sensor-driven one. Run once **per frequency** — set `RATEGROUP_HZ` and rebuild/redeploy the FSW binary at that frequency first. |
| `RunnerConfig_sample_rate_sweep.py` | Sensor sample-rate sweep | `nonsil`, `sil_snapshot`, `sil_lockstep`, `hil_snapshot`, `hil_lockstep` | Sweeps `SAMPLE_RATES` (5, 10, 25, 35, 50 Hz) as a factor, `time_step` held fixed at 0.001s. |
| `RunnerConfig_timestep_sweep.py` | ODE integration time-step sweep | `sil_snapshot`, `nonsil` | Sweeps `TIME_STEPS` (0.0001–0.01s) as a factor, `sample_rate` held fixed at 10Hz. HIL not included. |

All five configs share the same setup/teardown machinery (`_kill_fprime`, `_start_fprime`, `_kill_hil_fsw`, `_start_hil_fsw`) — keep any future fixes to those in sync across files.

---

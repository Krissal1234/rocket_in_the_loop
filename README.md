# Rocket-in-the-Loop (RITL)

**Masters Thesis Project** — Vrije University Amsterdam

A hardware/software-in-the-loop (HIL/SIL) framework that couples the [RocketPy](https://github.com/RocketPy-Team/RocketPy) 6-DOF flight simulator with real flight software (FSW) running on either a host machine or embedded hardware. The system was developed as part of a Masters thesis to evaluate different coupling architectures and their effect on simulated rocket flight fidelity and real-time performance, using the CAMÕES student rocket as the reference vehicle.

## Branches

- **`main`** — the RITL framework itself (orchestrator, coupling strategies, FSW adapters). No experiment automation.
- **`msc_thesis_submission`** (this branch) — a snapshot of `main` plus everything used to produce the thesis results: the `experiment_runner/` configs, fault injection, and the analysis scripts/plots.

---

## Overview

Traditional rocket simulation runs entirely in software with no feedback from real flight software. RITL closes this loop by:

1. Running RocketPy as the physics simulator.
2. Intercepting simulated sensor readings (barometer, accelerometer, gyroscope) at each ODE time-step.
3. Forwarding those readings to real FSW — either a process on localhost (SIL) or a binary on a Raspberry Pi over the network (HIL).
4. Receiving airbrake actuation commands and parachute deployment decisions back from the FSW.
5. Feeding those decisions back into RocketPy's controller callbacks, so the simulated flight is influenced by the real FSW.

The framework supports three operational modes:

| Mode | Description |
|---|---|
| `nonsil` | Pure simulation — RocketPy with a stub controller. Baseline for comparison. |
| `sil` | Software-in-the-Loop — FSW runs as a process on the same machine. |
| `hil` | Hardware-in-the-Loop — FSW binary runs on a Raspberry Pi reached via SSH/TCP. |

The FSW used in this thesis is built on [NASA F Prime](https://github.com/nasa/fprime).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Host machine                         │
│                                                             │
│  ┌────────────────┐    ZMQ REQ/REP     ┌─────────────────┐  │
│  │   RocketPy     │◄──────────────────►│                 │  │
│  │   Simulator    │  JSON over ZMQ     │   Orchestrator  │  │
│  │                │  tcp://127.0.0.1   │   (SimBridge)   │  │
│  │  SilController │  :5560             │                 │  │
│  └────────────────┘                    └────────┬────────┘  │
│                                                 │           │
│                             TCP (sensor) port   │           │
│                             TCP (actuation) port│           │
└─────────────────────────────────────────────────┼───────────┘
                                                  │
                        ┌─────────────────────────┼──────────┐
                        │  SIL: localhost         │          │
                        │  HIL: Raspberry Pi      │          │
                        │                         ▼          │
                        │              ┌──────────────────┐  │
                        │              │   F Prime FSW    │  │
                        │              │  (RitlFsw_SIL    │  │
                        │              │   Deployment)    │  │
                        │              └──────────────────┘  │
                        └────────────────────────────────────┘
```

The **Orchestrator** (`SimBridge`) is the central component. It sits between the simulator and the FSW, translating between two independent binary protocols and enforcing the chosen coupling strategy.

---

## Orchestrator Interfaces

### Simulator-side (ZMQ) Interface

The orchestrator binds a **ZMQ REP** socket on `tcp://127.0.0.1:5560` (configurable). The simulator (RocketPy via `SilController`) sends **JSON** messages as a ZMQ REQ client and waits for a JSON reply.

#### Message types (simulator → orchestrator)

**SENSOR** — sent on every airbrake controller callback (10 Hz by default):

```json
{
  "type":  "SENSOR",
  "t":     12.345,
  "baro":  85432.1,
  "accel": { "x": 0.01, "y": -0.02, "z": -9.81 },
  "gyro":  { "x": 0.001, "y": 0.002, "z": -0.001 }
}
```

**DROGUE_POLL** — sent on each parachute drogue trigger callback:

```json
{ "type": "DROGUE_POLL" }
```

**MAIN_POLL** — sent on each parachute main trigger callback:

```json
{ "type": "MAIN_POLL" }
```

#### Replies (orchestrator → simulator)

Reply to `SENSOR`:
```json
{ "airbrake_dep_level": 0.35 }
```

Reply to `DROGUE_POLL` / `MAIN_POLL`:
```json
{ "drogue": false, "main": false, "airbrake_dep_level": 0.35 }
```

The `airbrake_dep_level` is a float in `[0.0, 1.0]` representing the fraction of full airbrake deployment. RocketPy applies this directly to the aerodynamic drag model.

---

### FSW-side (TCP) Interface

The orchestrator communicates with F Prime FSW over **two separate TCP connections** using a compact binary protocol.

#### Sensor stream (orchestrator → FSW)

The orchestrator acts as a **TCP client** and connects to the FSW's sensor listener port (`fsw_sensor_port`, default `50100`).

Each sensor packet is **64 bytes** — eight `float64` values packed big-endian in this order:

| Byte offset | Field | Description |
|---|---|---|
| 0–7 | `t` | Simulation time (s) |
| 8–15 | `accel_x` | Accelerometer X (m/s²) |
| 16–23 | `accel_y` | Accelerometer Y (m/s²) |
| 24–31 | `accel_z` | Accelerometer Z (m/s²) |
| 32–39 | `baro` | Barometric pressure (Pa) |
| 40–47 | `gyro_x` | Gyroscope X (rad/s) |
| 48–55 | `gyro_y` | Gyroscope Y (rad/s) |
| 56–63 | `gyro_z` | Gyroscope Z (rad/s) |

After sending a packet the orchestrator waits for a **1-byte ACK** (`0x06`) from the FSW before continuing.

#### Actuation stream (FSW → orchestrator)

The orchestrator acts as a **TCP server** and listens on `fsw_actuation_port` (default `50101`). The FSW connects to this port and pushes actuation commands whenever its control loop produces output.

Each actuation command is a **9-byte** binary message:

| Byte | Field | Description |
|---|---|---|
| 0 | header byte | `0x01` |
| 1–8 | `airbrake_dep_level` | `float64` big-endian in `[0.0, 1.0]` |

The orchestrator stores the latest command in a thread-safe `FlagStore`. The coupling strategy then reads from this store to determine what to return to the simulator.

The same `FlagStore` snapshot is also returned in response to `DROGUE_POLL` / `MAIN_POLL`, including FSW-computed `drogue` and `main` boolean flags (if the FSW implementation sets them; otherwise the orchestrator uses its own logic).

---

## Coupling Strategies

The coupling strategy controls how tightly the simulator and FSW are synchronised. It is selected via `arch` in `config.yaml`.

### Lockstep (`arch: lockstep`)

The simulator **blocks** after each sensor update until the FSW returns a fresh airbrake command.

```
Sim  →  SENSOR  →  Orchestrator  →  send_sensor(FSW)
                                         ↓
Sim  ←  dep_level  ←  Orchestrator  ← wait_for_airbrake()
```

- Guarantees every sensor sample gets a response from the FSW.
- Simulation wall time increases because RocketPy's ODE integration stalls waiting for the FSW.
- Highest fidelity — the FSW sees every time-step.

### Snapshot (`arch: snapshot`)

The sensor is forwarded to the FSW asynchronously and the orchestrator **immediately returns** the last known actuation state from the `FlagStore`.

```
Sim  →  SENSOR  →  Orchestrator  →  send_sensor(FSW)  [no wait]
                        ↓
Sim  ←  dep_level  ←  get_snapshot()
```

- Simulation runs at full speed; FSW and simulator are decoupled in time.
- If the FSW is slower than the simulator, multiple sensor packets are queued before a new actuation arrives.
- Better wall-time performance at the cost of some phase lag in the control loop.

---

## Rate Group
This is the least synchronised strategy, however it uses non blocking RITL paired with a time-triggered FSW


## Fault Injection

The `FaultInjector` intercepts sensor data inside the orchestrator before it is forwarded to the FSW. It is configured in `config.yaml` under `fault_injection`.

| Parameter | Type | Description |
|---|---|---|
| `enabled` | bool | Activates fault injection. |
| `freeze_baro` | bool | Freezes the barometric pressure reading after a trigger time. |
| `freeze_baro_at` | float | Simulation time (s) at which to freeze the barometer. |
| `dropout_rate` | float | Probability `[0, 1]` of randomly dropping any sensor packet. |

When the barometer is frozen, the FSW continues to receive a stale pressure value while the true altitude (visible to RocketPy) continues to change. This tests the FSW's fault-detection and fallback logic.

---

## Configuration

All parameters for a single run are in `Ritl/config.yaml`:

```yaml
mode: sil               # nonsil | sil
arch: snapshot          # lockstep | snapshot | rategroup  (sil only)
rocket: cameos          # rocket model to simulate

log_dir: logs

network:
  fsw_host: 127.0.0.1   # FSW host — 127.0.0.1 for SIL, Pi IP for HIL
  fsw_sensor_port: 50100
  fsw_actuation_port: 50101
  zmq_address: tcp://127.0.0.1:5560

fault_injection:
  enabled: false
  freeze_baro: false
  freeze_baro_at: 10.0
  dropout_rate: 0.0

rocket_params:
  sample_rate: 10.0      # Hz — airbrake controller callback frequency
  time_step: 0.001       # s — RocketPy ODE integration time-step
```

`rategroup` reuses the same (non-blocking) coupling code as `snapshot` — see [Rate Group](#rate-group) below — it's paired with a time-triggered FSW build rather than a different coupling strategy in software.

---

## Running a Single Simulation

### Prerequisites

- Docker and Docker Compose installed.
- For SIL: F Prime GDS running with the `RitlFsw_SilDeployment` binary (see FSW repository).
- For HIL: Raspberry Pi accessible by SSH with the FSW binary deployed.

### Non-SIL (baseline, no FSW required)

```bash
cd Ritl
# Edit config.yaml: set mode: nonsil
docker compose up
```

### SIL

```bash
# 1. Start F Prime GDS on the host machine (in the FSW repo):
source fprime-venv/bin/activate
cd RitlFsw/SilDeployment
fprime-gds

# 2. Edit Ritl/config.yaml:
#    mode: sil
#    arch: lockstep   (or snapshot)
#    network.fsw_host: 127.0.0.1

# 3. Run the simulation:
cd Ritl
docker compose up
```

### HIL

```bash
# 1. SSH to the Pi and start the FSW binary:
ssh pi@10.42.0.142
./RitlFsw_SilDeployment

# 2. Edit Ritl/config.yaml:
#    mode: sil
#    arch: lockstep   (or snapshot)
#    network.fsw_host: 10.42.0.142

# 3. Run the simulation from the host:
cd Ritl
docker compose up
```

## Experiment Runner

*(only on `msc_thesis_submission` — `main` does not include this)*

The experiment runner automates multi-run comparative experiments across all modes. It is built on the [experiment-runner](https://github.com/S2-group/experiment-runner) framework. Five standalone configs live in `experiment_runner/`, one per experiment (coupling-strategy comparison, fault injection, rate-group frequency sweep, sample-rate sweep, time-step sweep) — see [`experiment_runner/Readme.md`](experiment_runner/Readme.md) for the full list, what each one sweeps, and how to run it.

---

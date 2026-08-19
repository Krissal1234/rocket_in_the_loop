# Rocket-in-the-Loop (RITL)

**Masters Thesis Project** — Joint degree: University of Amsterdam and Vrije Universiteit

RITL is a framework for coupling a flight simulator with real flight software (FSW) in a closed feedback loop, for Software/Hardware-in-the-Loop (SIL/HIL) testing of flight control code. RITL is designed for both the simulator and the FSW to be swappable rather than hardcoded to one toolchain.

Right now:
- **Simulator backend:** [RocketPy](https://github.com/RocketPy-Team/RocketPy). An **FMU** backend is in progress.

- **FSW backend:** [NASA F Prime](https://github.com/nasa/fprime). Other flight software frameworks can be added the same way.

## How it works

The simulator streams sensor data to the FSW at each time-step; the FSW streams back actuation commands (airbrake, parachute deployment) that feed back into the simulated flight. A `SimBridge` sits in between and applies the selected coupling strategy (`blocking` or `non_blocking`), and optional fault injection (dropped packets, frozen sensor values) for testing FSW fault handling.

## Installation

Requires Python ≥3.10.

```bash
git clone https://github.com/Krissal1234/rocket_in_the_loop.git
cd rocket_in_the_loop
pip install -e .
```

## Usage

**`main.py`** runs a simulation from a config file. This is the normal way to run RITL:

```bash
python main.py --config configs/default.yaml
```

Edit `configs/default.yaml` to set the mode (`sil`/`nonsil`), simulator, rocket, network settings, and fault injection.

**`examples/`** shows how to use RITL as a library instead. Building a bridge, coupling strategy, and driver directly in Python for custom setups.

## F Prime companion project

RITL doesn't ship an F Prime deployment — you need a compatible one running before starting a `sil`mode run.

- Use the tag/branch that matches this RITL version: **`<version/tag to pin here>`**

## Status

RocketPy + F Prime is the only combination currently working end-to-end. FMU-based simulation support is in progress and will slot in alongside RocketPy without changing the rest of the stack.
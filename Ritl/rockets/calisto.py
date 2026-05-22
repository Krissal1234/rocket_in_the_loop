# rockets/calisto.py
import logging
from rocketpy import Flight, Rocket, SolidMotor, Environment
from rocketpy import Accelerometer, Barometer, Gyroscope

log = logging.getLogger("ritl.rocketpy")

_ROCKETPY_DATA = "data/Calisto_flight"


def build(controller, enable_sil: bool = False) -> Flight:
    env = _build_environment()
    motor = _build_motor()
    rocket = _build_rocket(motor)
    _add_sensors(rocket)
    _add_controllers(rocket, controller, enable_sil)
    _add_parachutes(rocket, controller)
    return _run(rocket, env)


def _build_environment():
    log.info("building environment...")
    env = Environment(
        latitude=32.990254,
        longitude=-106.974998,
        elevation=1400,
    )
    env.set_atmospheric_model(
        type="custom_atmosphere",
        wind_u=[(0, 3), (10000, 3)],
        wind_v=[(0, 5), (10000, -5)],
    )
    return env


def _build_motor():
    log.info("building motor...")
    return SolidMotor(
        thrust_source=f"{_ROCKETPY_DATA}/Cesaroni_M1670.eng",
        dry_mass=1.815,
        dry_inertia=(0.125, 0.125, 0.002),
        nozzle_radius=33 / 1000,
        grain_number=5,
        grain_density=1815,
        grain_outer_radius=33 / 1000,
        grain_initial_inner_radius=15 / 1000,
        grain_initial_height=120 / 1000,
        grain_separation=5 / 1000,
        grains_center_of_mass_position=0.397,
        center_of_dry_mass_position=0.317,
        nozzle_position=0,
        burn_time=3.9,
        throat_radius=11 / 1000,
        coordinate_system_orientation="nozzle_to_combustion_chamber",
    )


def _build_rocket(motor):
    log.info("building rocket...")
    rocket = Rocket(
        radius=127 / 2000,
        mass=14.426,
        inertia=(6.321, 6.321, 0.034),
        power_off_drag=f"{_ROCKETPY_DATA}/powerOffDragCurve.csv",
        power_on_drag=f"{_ROCKETPY_DATA}/powerOnDragCurve.csv",
        center_of_mass_without_motor=0,
        coordinate_system_orientation="tail_to_nose",
    )
    rocket.set_rail_buttons(
        upper_button_position=0.0818,
        lower_button_position=-0.618,
        angular_position=45,
    )
    rocket.add_motor(motor, position=-1.255)
    rocket.add_nose(length=0.55829, kind="vonKarman", position=1.278)
    rocket.add_trapezoidal_fins(
        n=4,
        root_chord=0.120,
        tip_chord=0.060,
        span=0.110,
        position=-1.04956,
        cant_angle=0.5,
        airfoil=(f"{_ROCKETPY_DATA}/NACA0012-radians.txt", "radians"),
    )
    rocket.add_tail(
        top_radius=0.0635, bottom_radius=0.0435, length=0.060, position=-1.194656
    )
    return rocket


def _add_sensors(rocket):
    log.info("adding sensors...")
    accel = Accelerometer(sampling_rate=10, consider_gravity=False, name="IMU")
    baro  = Barometer(sampling_rate=10, name="Barometer")
    gyro  = Gyroscope(sampling_rate=10, name="Gyroscope")
    rocket.add_sensor(accel, -0.10482544178314143)
    rocket.add_sensor(baro,  -0.10482544178314143)
    rocket.add_sensor(gyro,  -0.10482544178314143)


def _add_controllers(rocket, ctrl, enable_sil):
    log.info("adding controllers...")

    rocket.add_air_brakes(
        drag_coefficient_curve=f"{_ROCKETPY_DATA}/air_brakes_cd.csv",
        controller_function=ctrl.airbrake_controller,
        name="AirBrakes",
        controller_name="AirBrakesController",
        sampling_rate=10,
        reference_area=None,
        clamp=True,
        initial_observed_variables=(0, 0),
        override_rocket_drag=False,  # calisto uses additive drag, not override
    )


def _add_parachutes(rocket, ctrl):
    log.info("adding parachutes...")
    rocket.add_parachute(
        name="drogue", cd_s=1.0, trigger=ctrl.drogue_trigger,
        sampling_rate=100, lag=1.5, noise=(0, 8.3, 0.5),
    )
    rocket.add_parachute(
        name="main", cd_s=10.0, trigger=ctrl.main_trigger,
        sampling_rate=100, lag=1.5, noise=(0, 8.3, 0.5),
    )


def _run(rocket, env):
    log.info("running simulation...")
    return Flight(
        rocket=rocket,
        environment=env,
        rail_length=5.2,
        inclination=85,
        heading=0,
        max_time_step=0.001,
        min_time_step=0.001,
        time_overshoot=False,
    )
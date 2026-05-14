import logging
from rocketpy import Flight, Rocket, SolidMotor, Environment
from rocketpy import Accelerometer, Barometer, Gyroscope

log = logging.getLogger("ritl.rocketpy")

DATA = "data/Camoes_flight"


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
        gravity=9.80665,
        date=(2023, 10, 14, 14),
        latitude=39.3900032043457,
        longitude=-8.2895383834838,
        elevation=107,
        datum="WGS84",
        timezone="Portugal",
    )
    env.set_atmospheric_model(
        type="Reanalysis",
        file=f"{DATA}/euroc_2023_all_windows.nc",
        dictionary="ECMWF",
    )
    env.max_expected_height = 4000
    return env


def _build_motor():
    log.info("building motor...")
    return SolidMotor(
        thrust_source=f"{DATA}/thrust_source.csv",
        burn_time=3.72,
        grain_number=6,
        grain_density=1637,
        grain_initial_inner_radius=0.015,
        grain_outer_radius=0.045,
        grain_initial_height=0.15,
        nozzle_radius=0.034,
        throat_radius=0.0135,
        grain_separation=0.005,
        grains_center_of_mass_position=-0.7566,
        dry_inertia=(0, 0, 0),
        center_of_dry_mass_position=0,
        dry_mass=0,
        nozzle_position=-1.3346,
    )


def _build_rocket(motor):
    log.info("building rocket...")
    rocket = Rocket(
        radius=0.0715,
        mass=22.8,
        inertia=(16.2, 16.2, 0.066),
        center_of_mass_without_motor=0,
        power_off_drag=f"{DATA}/drag_coefficient_power_off.csv",
        power_on_drag=f"{DATA}/drag_coefficient_power_on.csv",
        coordinate_system_orientation="tail_to_nose",
    )
    rocket.add_motor(motor, position=0)
    rocket.set_rail_buttons(0.5, 0.2)
    rocket.add_nose(length=0.455, kind="vonKarman", position=1.1884)
    rocket.add_trapezoidal_fins(
        n=4,
        span=0.155,
        root_chord=0.185,
        tip_chord=0.15,
        position=-1.0866,
    )
    rocket.add_tail(
        top_radius=0.0715, bottom_radius=0.037, length=0.048, position=-1.2866
    )
    return rocket


def _add_sensors(rocket):
    log.info("adding sensors...")
    accel = Accelerometer(sampling_rate=10, consider_gravity=False, name="IMU")
    baro  = Barometer(sampling_rate=10, name="Barometer")
    gyro  = Gyroscope(sampling_rate=10, name="Gyroscope")
    rocket.add_sensor(accel, position=0.5)
    rocket.add_sensor(baro,  position=0.5)
    rocket.add_sensor(gyro,  position=0.5)


def _add_controllers(rocket, ctrl, enable_sil):
    log.info("adding controllers...")
    if enable_sil:
        rocket.add_air_brakes(
            drag_coefficient_curve=[[0, 0, 0.0], [0, 0, 0.0], [0, 0, 0.0], [0, 0, 0.0]],
            controller_function=ctrl.sensor_controller,
            sampling_rate=10,
            name="SensorTransmitter",
            controller_name="SensorTransmitterController",
        )
    rocket.add_air_brakes(
        drag_coefficient_curve=f"{DATA}/drag_airbrakes.csv",
        controller_function=ctrl.airbrake_controller,
        name="AirBrakes",
        controller_name="AirBrakesController",
        sampling_rate=10,
        reference_area=None,
        clamp=True,
        initial_observed_variables=(0, 0),
        override_rocket_drag=True,
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
        max_time_step=0.001,
        min_time_step=0.001,
        rail_length=12,
        inclination=84,
        heading=133,
        time_overshoot=False,
    )
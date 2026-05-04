import logging
import datetime
from rocketpy import Flight, Rocket, SolidMotor, Environment
from rocketpy import Accelerometer, Barometer, Gyroscope
from .rocketpy_controllers import RocketPyControllers


log = logging.getLogger("ritl.rocketpy")

class FlightBuilder:

    def __init__(self, enable_sil, controllers : RocketPyControllers, data_folder: str = "data"):
        self.env = None
        self.motor = None
        self.rocket = None
        self.flight = None
        self.data_folder = data_folder
        self.ctrl = controllers
        self.enable_sil = enable_sil

    def build(self) -> Flight:
        self._build_environment()
        self._build_motor()
        self._build_rocket()
        self._add_sensors()
        self._add_controllers()
        self._add_parachutes()
        self._run()
        return self.flight

    def _build_environment(self):
        log.info("building environment...")
        self.env = Environment(
            gravity=9.80665,
            date=(2023, 10, 14, 14),
            latitude=39.3900032043457,
            longitude=-8.2895383834838,
            elevation=107,
            datum="WGS84",
            timezone="Portugal",
        )

        self.env.set_atmospheric_model(
            type="Reanalysis",
            file= f"{self.data_folder}/euroc_2023_all_windows.nc",
            dictionary="ECMWF",
        )
        self.env.max_expected_height = 4000



    def _build_motor(self):
        log.info("building motor...")
        self.motor = SolidMotor(
            thrust_source = f"{self.data_folder}/thrust_source.csv",
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
            nozzle_position=-1.3346
        )

    def _build_rocket(self):
        log.info("building rocket...")

        self.rocket = Rocket(
            radius=0.0715,
            mass=22.8,
            inertia=(16.2, 16.2, 0.066),
            center_of_mass_without_motor=0,
            power_off_drag = f"{self.data_folder}/drag_coefficient_power_off.csv",
            power_on_drag = f"{self.data_folder}/drag_coefficient_power_on.csv",
            coordinate_system_orientation="tail_to_nose",
        )

        self.rocket.add_motor(self.motor, position=0)

        self.rocket.set_rail_buttons(0.5, 0.2)

        self.rocket.add_nose( length=0.455, kind="vonKarman", position=1.1884)

        self.rocket.add_trapezoidal_fins(
            n=4,
            span=0.155,
            root_chord=0.185,
            tip_chord=0.15,
            position=-1.0866,
        )

        self.rocket.add_tail(
            top_radius=0.0715, bottom_radius=0.037, length=0.048, position=-1.2866
        )


    def _add_sensors(self):
        log.info("adding sensors...")
        accel = Accelerometer(sampling_rate=10, consider_gravity=False, name="IMU")
        baro  = Barometer(sampling_rate=10, name="Barometer")
        gyro  = Gyroscope(sampling_rate=10, name="Gyroscope")

        self.rocket.add_sensor(accel, position=0.5)
        self.rocket.add_sensor(baro,  position=0.5)
        self.rocket.add_sensor(gyro,  position=0.5)

    def _add_controllers(self):
        log.info("adding controllers...")


        # At the time of development, rocketpy does not include custom controllers
        # Airbrakes currently serve as a dummy controller simply to send sensor data to orchestrator
        if self.enable_sil:
            self.rocket.add_air_brakes(
                drag_coefficient_curve=[[0, 0, 0.0], [0, 0, 0.0], [0, 0, 0.0], [0, 0, 0.0]],
                controller_function=self.ctrl.sensor_controller,
                sampling_rate=10,
                name="SensorTransmitter",
                controller_name="SensorTransmitterController",
            )

        self.rocket.add_air_brakes(
            drag_coefficient_curve=f"{self.data_folder}/drag_airbrakes.csv",
            controller_function=self.ctrl.airbrake_controller if self.enable_sil else self.ctrl.airbrake_controller_non_sim,
            name="AirBrakes",
            controller_name="AirBrakesController",
            sampling_rate=10,
            reference_area=None,
            clamp=True,
            initial_observed_variables=(0,0),
            override_rocket_drag=True,
        )

    def _add_parachutes(self):
        log.info("adding parachutes...")
        self.rocket.add_parachute(
            name="drogue",
            cd_s=1.0,
            trigger=self.ctrl.drogue_trigger if self.enable_sil else self.ctrl.drogue_trigger_non_sim,
            sampling_rate=100,
            lag=1.5,
            noise=(0, 8.3, 0.5),
        )
        self.rocket.add_parachute(
            name="main",
            cd_s=10.0,
            trigger=self.ctrl.main_trigger if self.enable_sil else self.ctrl.main_trigger_non_sim,
            sampling_rate=100,
            lag=1.5,
            noise=(0, 8.3, 0.5),
        )

    def _run(self):
        log.info("running simulation...")
        self.flight = Flight(
            rocket=self.rocket,
            environment=self.env,
            max_time_step = 0.001,
            # min_time_step = 0.001,
            rail_length=12,
            inclination=84,
            heading=133,
            time_overshoot=False,
        )

def build_flight(enable_sil, data_folder, controllers: RocketPyControllers) -> Flight:
    return FlightBuilder(enable_sil, data_folder, controllers).build()
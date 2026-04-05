import logging
import datetime
from rocketpy import Flight, Rocket, SolidMotor, Environment
from rocketpy import Accelerometer, Barometer, Gyroscope
from .rocketpy_controllers import RocketPyControllers


log = logging.getLogger("ritl.rocketpy")

class FlightBuilder:

    def __init__(self, controllers : RocketPyControllers, data_folder: str = "data"):
        self.env = None
        self.motor = None
        self.rocket = None
        self.flight = None
        self.data_folder = data_folder
        self.ctrl = controllers

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
            latitude=39.389700,
            longitude=-8.288964,
            elevation=113,
        )
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        self.env.set_date((tomorrow.year, tomorrow.month, tomorrow.day, 12))



    def _build_motor(self):
        log.info("building motor...")
        self.motor = SolidMotor(
            thrust_source=f"{self.data_folder}/Cesaroni_M1670.eng",
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

    def _build_rocket(self):
        log.info("building rocket...")

        self.rocket = Rocket(
            radius=127 / 2000,
            mass=14.426,
            inertia=(6.321, 6.321, 0.034),
            power_off_drag=f"{self.data_folder}/powerOffDragCurve.csv",
            power_on_drag=f"{self.data_folder}/powerOnDragCurve.csv",
            center_of_mass_without_motor=0,
            coordinate_system_orientation="tail_to_nose",
        )

        self.rocket.add_motor(self.motor, position=-1.255)

        self.rocket.set_rail_buttons(
            upper_button_position=0.0818,
            lower_button_position=-0.618,
            angular_position=45,
        )

        self.rocket.add_nose(length=0.55829, kind="vonKarman", position=1.278)

        self.rocket.add_trapezoidal_fins(
            n=4,
            root_chord=0.120,
            tip_chord=0.060,
            span=0.110,
            position=-1.04956,
            cant_angle=0.5,
            airfoil=(f"{self.data_folder}/NACA0012-radians.txt", "radians"),
        )

        self.rocket.add_tail(
            top_radius=0.0635, bottom_radius=0.0435, length=0.060, position=-1.194656
        )


    def _add_sensors(self):
        log.info("adding sensors...")
        accel = Accelerometer(sampling_rate=100, consider_gravity=False, name="IMU")
        baro  = Barometer(sampling_rate=100, name="Barometer")
        gyro  = Gyroscope(sampling_rate=100, name="Gyroscope")

        self.rocket.add_sensor(accel, position=0.5)
        self.rocket.add_sensor(baro,  position=0.5)
        self.rocket.add_sensor(gyro,  position=0.5)

    def _add_controllers(self):
        log.info("adding controllers...")


        # At the time of development, rocketpy does not include custom controllers
        # Airbrakes currently serve as a dummy controller simply to send sensor data to orchestrator
        self.rocket.add_air_brakes(
            drag_coefficient_curve=[[0, 0, 0.0], [1, 0, 0.0], [0, 1, 0.0], [1, 1, 0.0]],
            controller_function=self.ctrl.sensor_controller,
            sampling_rate=100,
            name="SensorTransmitter",
            controller_name="SensorTransmitterController",
        )

        # Real Airbrakes
        # self.rocket.add_air_brakes(
        #     drag_coefficient_curve=f"{self.data_folder}/airbrakes_cd.csv",
        #     controller_function=self.ctrl.airbrake_controller,
        #     sampling_rate=100,
        #     name="AirBrakes",
        #     controller_name="AirBrakesController",
        # )

    def _add_parachutes(self):
        log.info("adding parachutes...")
        self.rocket.add_parachute(
            name="drogue",
            cd_s=1.0,
            trigger=self.ctrl.drogue_trigger,
            sampling_rate=100,
            lag=1.5,
            noise=(0, 8.3, 0.5),
        )
        self.rocket.add_parachute(
            name="main",
            cd_s=10.0,
            trigger=self.ctrl.main_trigger,
            sampling_rate=100,
            lag=1.5,
            noise=(0, 8.3, 0.5),
        )

    def _run(self):
        log.info("running simulation...")
        self.flight = Flight(
            rocket=self.rocket,
            environment=self.env,
            rail_length=5.2,
            inclination=85,
            heading=0,
            time_overshoot=False,
        )

def build_flight(data_folder, controllers: RocketPyControllers) -> Flight:
    return FlightBuilder(data_folder, controllers).build()
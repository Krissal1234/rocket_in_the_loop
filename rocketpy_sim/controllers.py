import logging
log = logging.getLogger("ritl.controllers")


_flags = {
    "drogue": False,
    "main":   False,
}

def set_flag(channel: str, value: bool):
    log.info(f"flag set: {channel}={value}")
    _flags[channel] = value

def sensor_controller(time, sampling_rate, state, state_history,
                      observed_variables, air_brakes, sensors):

    accel = sensors[0].measurement # xyz
    baro  = sensors[1].measurement
    gyro  = sensors[2].measurement # xyz



    return time

def airbrake_controller(time, sampling_rate, state, state_history,
                        observed_variables, air_brakes, sensors):

    return time, air_brakes.deployment_level

def drogue_trigger(pressure, height, state):
    return _flags["drogue"]

def main_trigger(pressure, height, state):
    return _flags["main"]
import logging

log = logging.getLogger("ritl.controllers.non_sil")


TARGET_APOGEE = 3000

# air-brake PI
Kp             = 0.001
Ki             = 0.0001
BOOST_ACCEL_THRESHOLD = 15.0 #— below this after boost means burnout
INTEGRAL_CLAMP = 1000.0

# baro-based apogee detection
APOGEE_BARO_DELTA    = 0.5
APOGEE_CONFIRM_COUNT = 5

MAIN_DEPLOY_DELTA_HPA = 40.0


class NonSilControllers:
    def __init__(self):
        self._last_time = None
        self._pid = {
            "integral": 0.0,
            "prev_dep": 0.0,
            "vz": 0.0,
            "prev_alt": None,
            "burned_out": False,
            "descent_count": 0,
            "P0": None,
        }
        self._recovery = {
            "min_baro": float("inf"),
            "baro_count": 0,
            "drogue_fired": False,
            "main_fired": False,
        }

    def _baro_update(self, p_hpa: float) -> None:
        r = self._recovery
        if not r["drogue_fired"]:
            if p_hpa < r["min_baro"]:
                r["min_baro"]   = p_hpa
                r["baro_count"] = 0
            elif p_hpa > r["min_baro"] + APOGEE_BARO_DELTA:
                r["baro_count"] += 1

    def drogue_trigger(self, pressure, height, state) -> bool:
        r = self._recovery
        self._baro_update(pressure / 100.0)  # Pa → hPa

        if not r["drogue_fired"] and r["baro_count"] >= APOGEE_CONFIRM_COUNT:
            r["drogue_fired"] = True
            # log.info("Drogue fired at pressure=%.2f hPa", pressure / 100.0)

        return r["drogue_fired"]

    def main_trigger(self, pressure, height, state) -> bool:
        r = self._recovery
        if r["drogue_fired"] and not r["main_fired"]:
            if (pressure / 100.0) >= r["min_baro"] + MAIN_DEPLOY_DELTA_HPA:
                r["main_fired"] = True
                # log.info("Main chute fired at pressure=%.2f hPa", pressure / 100.0)

        return r["main_fired"]



    def airbrake_controller(self, time,sampling_rate,state_vector, state_history, observed_variables, air_brakes, sensors, environment):
      # guard becuase controllers are called twice
        if time == self._last_time:
            return time

        dt = (time - self._last_time) if self._last_time is not None else 1.0 / sampling_rate
        self._last_time = time

        accel = sensors[0].measurement
        pressure = sensors[1].measurement

        ax, ay, az = accel
        pid = self._pid

        # get ground pressure on first call
        if pid["P0"] is None:
            pid["P0"] = pressure
            air_brakes.deployment_level = 0
            return time

        pid["vz"] += az * dt

        if not pid["burned_out"]:
            if az < BOOST_ACCEL_THRESHOLD:
                pid["burned_out"] = True
                log.info("Burnout detected at t=%.2f s", time)
            else:
                air_brakes.deployment_level = 0
                return time

        altitude = 44330.0 * (1.0 - (pressure / pid["P0"]) ** (1.0 / 5.255))

        if pid["prev_alt"] is not None:
            if altitude < pid["prev_alt"]:
                pid["descent_count"] += 1
            else:
                pid["descent_count"] = 0

        if pid["descent_count"] >= 10:
            air_brakes.deployment_level = 0
            pid["integral"] = 0.0
            pid["vz"]       = 0.0
            pid["prev_alt"] = altitude
            return time

        pid["prev_alt"] = altitude

        vz               = pid["vz"]
        predicted_apogee = altitude + (vz ** 2) / (2 * 9.81)

        # PI control
        error             = predicted_apogee - TARGET_APOGEE
        pid["integral"]  += error * dt
        pid["integral"]   = max(-INTEGRAL_CLAMP, min(INTEGRAL_CLAMP, pid["integral"]))

        raw     = Kp * error + Ki * pid["integral"]
        new_dep = max(0.0, min(1.0, raw))

        # log.info(
        #     "t=%.2f alt=%.1f pred=%.1f err=%.1f dep=%.3f vz=%.2f",
        #     time, altitude, predicted_apogee, error, new_dep, vz,
        # )

        if new_dep > 0 or air_brakes.deployment_level > 0:
            log.info(f"DEP {time:.4f} {new_dep:.6f}")

        air_brakes.deployment_level = new_dep
        return time

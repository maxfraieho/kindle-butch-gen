# -*- coding: utf-8 -*-
"""
Thermal Backoff Engine for Vydra (kindle-butch-gen).
Monitors SoC / Battery temperature via Android sysfs & Termux:API.
Enforces thermal hysteresis sleep loops to prevent CPU throttling & OS thermal crashes.
"""

import os
import time
import json
import subprocess
import logging

logger = logging.getLogger("VydraThermal")

class ThermalBackoffEngine:
    def __init__(self, high_threshold=65.0, low_threshold=55.0, check_interval=10):
        self.high_threshold = float(high_threshold)
        self.low_threshold = float(low_threshold)
        self.check_interval = int(check_interval)


    def _read_sysfs_temp(self) -> float:
        max_temp = 0.0
        # BMS & Battery temperature paths
        bms_paths = [
            "/sys/class/power_supply/bms/temp",
            "/sys/class/power_supply/battery/temp"
        ]
        for path in bms_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        val = float(f.read().strip())
                        temp_c = val / 10.0 if val < 1000 else val / 1000.0
                        if 20.0 <= temp_c <= 80.0:
                            max_temp = max(max_temp, temp_c)
                except Exception:
                    pass

        # CPU / SoC Thermal Zones
        thermal_base = "/sys/class/thermal"
        if os.path.exists(thermal_base):
            try:
                for zone in os.listdir(thermal_base):
                    if zone.startswith("thermal_zone"):
                        temp_file = os.path.join(thermal_base, zone, "temp")
                        if os.path.exists(temp_file):
                            with open(temp_file, "r") as f:
                                val = float(f.read().strip())
                                # No "raw value is already whole-degree C"
                                # fallback here on purpose: confirmed live on
                                # this device that a non-temperature zone
                                # (type=socd, raw=69) silently passes the
                                # plausibility range as "69.0C" under that
                                # assumption, overriding every real millidegree
                                # reading (cpu/gpu/battery/shell zones all sat
                                # at 34-43C at the time) via max(). Every real
                                # temperature zone observed on this hardware
                                # reports in millidegree C (raw > 1000); a
                                # small raw value is far more likely to be an
                                # unrelated non-temperature zone (bcl-lvl,
                                # ibat-lvl, socd, vbat, usb) than a genuine
                                # sub-100C-as-whole-degrees reading, so such
                                # zones are skipped entirely rather than
                                # guessed at.
                                if val > 1000:
                                    temp_c = val / 1000.0
                                elif val > 100:
                                    temp_c = val / 10.0
                                else:
                                    continue
                                if 20.0 <= temp_c <= 95.0:
                                    max_temp = max(max_temp, temp_c)
            except Exception:
                pass

        return max_temp

    def _read_termux_api_temp(self) -> float:
        try:
            res = subprocess.run(
                ["termux-battery-status"], capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return float(data.get("temperature", 0.0))
        except Exception:
            pass
        return 0.0

    def get_current_temperature(self) -> float:
        temp = self._read_sysfs_temp()
        if temp == 0.0:
            temp = self._read_termux_api_temp()
        return temp

    def enforce_thermal_limits(self):
        current_temp = self.get_current_temperature()
        if current_temp >= self.high_threshold:
            logger.warning(
                f"🔥 [Thermal Guard] Досягнуто термопорогу: {current_temp:.1f}°C >= {self.high_threshold}°C. "
                f"Пауза для охолодження..."
            )
            print(
                f"\n⚠️ [Thermal Guard] Досягнуто термопорогу: {current_temp:.1f}°C >= {self.high_threshold}°C. "
                f"Пауза для охолодження..."
            )
            while current_temp > self.low_threshold:
                time.sleep(self.check_interval)
                current_temp = self.get_current_temperature()
                if current_temp > 0:
                    logger.info(
                        f"❄️ [Thermal Guard] Охолодження: поточна T = {current_temp:.1f}°C "
                        f"(ціль: <{self.low_threshold}°C)..."
                    )
                    print(
                        f"❄️ [Thermal Guard] Охолодження: {current_temp:.1f}°C -> ціль <{self.low_threshold}°C..."
                    )
            logger.info(f"✅ [Thermal Guard] Охолодження завершено: {current_temp:.1f}°C. Відновлення роботи.")
            print(f"✅ [Thermal Guard] Охолодження завершено: {current_temp:.1f}°C. Відновлення роботи.\n")

# Global default instance for easy import
thermal_guard = ThermalBackoffEngine(high_threshold=65.0, low_threshold=55.0)


import logging
import math
import os
import signal
import threading
import time

from prometheus_client import Gauge, Counter, start_http_server
from pysolarmanv5 import PySolarmanV5

HOST = os.getenv("DEYE_HOST", "192.168.50.4")
PORT = int(os.getenv("DEYE_PORT", "8899"))
SERIAL = os.getenv("DEYE_SERIAL")
INTERVAL = int(os.getenv("DEYE_POLL_INTERVAL", "60"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "9808"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("deye-exporter")

up = Gauge("deye_inverter_up", "Successful inverter polling")
last_success = Gauge(
    "deye_last_success_timestamp_seconds",
    "Unix timestamp of last successful polling",
)
errors = Counter(
    "deye_poll_errors_total",
    "Total failed inverter polling attempts",
)

metrics = {
    "daily": Gauge("deye_energy_today_kwh", "Daily energy generation in kWh"),
    "total": Gauge("deye_energy_total_kwh", "Total energy generation in kWh"),
    "ac_voltage": Gauge("deye_ac_voltage_volts", "AC voltage in volts"),
    "ac_current": Gauge("deye_ac_current_amperes", "AC current in amperes"),
    "ac_frequency": Gauge("deye_ac_frequency_hertz", "AC frequency in Hz"),
    "pv1_voltage": Gauge("deye_pv1_voltage_volts", "PV1 voltage in volts"),
    "pv1_current": Gauge("deye_pv1_current_amperes", "PV1 current in amperes"),
    "pv1_power": Gauge("deye_pv1_power_watts", "Calculated PV1 DC power in watts"),
    "pv2_voltage": Gauge("deye_pv2_voltage_volts", "PV2 voltage in volts"),
    "pv2_current": Gauge("deye_pv2_current_amperes", "PV2 current in amperes"),
    "pv2_power": Gauge("deye_pv2_power_watts", "Calculated PV2 DC power in watts"),
}

stop_event = threading.Event()


def stop_handler(signum, frame):
    log.info("Shutdown requested")
    stop_event.set()


def read_register(client, address, quantity=1):
    values = client.read_holding_registers(
        register_addr=address,
        quantity=quantity,
    )
    if len(values) != quantity:
        raise RuntimeError(f"Invalid response for register {address}")
    return values


def collect():
    client = None

    try:
        client = PySolarmanV5(
            HOST,
            int(SERIAL),
            port=PORT,
            mb_slave_id=1,
            timeout=10,
        )

        daily = read_register(client, 60)[0] / 10
        time.sleep(0.3)

        total_words = read_register(client, 63, 2)
        total = (total_words[0] + total_words[1] * 65536) / 10
        time.sleep(0.3)

        ac_voltage = read_register(client, 73)[0] / 10
        time.sleep(0.3)

        ac_current = read_register(client, 76)[0] / 10
        time.sleep(0.3)

        ac_frequency = read_register(client, 79)[0] / 100
        time.sleep(0.3)

        pv1 = read_register(client, 109, 2)
        time.sleep(0.3)

        pv2 = read_register(client, 111, 2)

        values = {
            "daily": daily,
            "total": total,
            "ac_voltage": ac_voltage,
            "ac_current": ac_current,
            "ac_frequency": ac_frequency,
            "pv1_voltage": pv1[0] / 10,
            "pv1_current": pv1[1] / 10,
            "pv2_voltage": pv2[0] / 10,
            "pv2_current": pv2[1] / 10,
        }

        values["pv1_power"] = values["pv1_voltage"] * values["pv1_current"]
        values["pv2_power"] = values["pv2_voltage"] * values["pv2_current"]

        for key, value in values.items():
            metrics[key].set(value)

        last_success.set(time.time())
        up.set(1)

        log.info(
            "Polling OK | PV1 %.1f W | PV2 %.1f W | Today %.1f kWh",
            values["pv1_power"],
            values["pv2_power"],
            daily,
        )

    except Exception:
        up.set(0)
        errors.inc()

        for metric in metrics.values():
            metric.set(math.nan)

        log.exception("Polling failed")

    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                log.warning("Error disconnecting from datalogger")


def main():
    if not SERIAL or not SERIAL.isdigit() or len(SERIAL) != 10:
        raise ValueError("DEYE_SERIAL must contain exactly 10 digits")

    if INTERVAL < 30:
        raise ValueError("DEYE_POLL_INTERVAL must be at least 30 seconds")

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    up.set(0)

    start_http_server(METRICS_PORT, addr="0.0.0.0")
    log.info("Metrics endpoint listening on port %s", METRICS_PORT)

    while not stop_event.is_set():
        started = time.monotonic()
        collect()
        elapsed = time.monotonic() - started
        stop_event.wait(max(0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()

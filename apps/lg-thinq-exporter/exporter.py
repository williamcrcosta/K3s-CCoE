import asyncio
import logging
import math
import os
import time
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout
from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import GaugeMetricFamily
from psycopg import AsyncConnection
from thinqconnect import USAGE_DAILY
from thinqconnect.thinq_api import ThinQAPIException, ThinQApi

LOG = logging.getLogger("lg-thinq")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
STATE_INTERVAL = 60
ENERGY_INTERVAL = 3600
POWER = {"POWER_ON": 1, "POWER_OFF": 0}
STATE_LABELS = {
    "mode": ("airConJobMode", "currentJobMode"),
    "fan": ("airFlow", "windStrength"),
    "fan_detail": ("airFlow", "windStrengthDetail"),
    "swing": ("windDirection", "rotateUpDown"),
    "display": ("display", "light"),
    "run_state": ("runState", "currentState"),
    "start_timer": ("timer", "relativeStartTimer"),
    "stop_timer": ("timer", "relativeStopTimer"),
    "sleep_timer": ("sleepTimer", "relativeStopTimer"),
}


def state_metrics(state):
    operation = (state.get("operation") or {}).get("airConOperationMode")
    values = {}
    if operation in POWER:
        values["power_on"] = POWER[operation]

    temperature = state.get("temperature") or {}
    if temperature.get("unit") != "C":
        temperature = next(
            (reading for reading in (state.get("temperatureInUnits") or [])
             if reading.get("unit") == "C"), {}
        )
    filters = state.get("filterInfo") or {}
    for metric, value in {
        "room_temperature_celsius": temperature.get("currentTemperature"),
        "target_temperature_celsius": temperature.get("targetTemperature"),
        "filter_used_time_raw": filters.get("usedTime"),
        "filter_lifetime_raw": filters.get("filterLifetime"),
    }.items():
        if type(value) in (int, float) and math.isfinite(value):
            values[metric] = value

    labels = {}
    for label, (group, key) in STATE_LABELS.items():
        value = (state.get(group) or {}).get(key)
        labels[label] = "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
    return values, labels


def energy_rows(response, first_day, last_day):
    if not isinstance(response, dict) or response.get("resultCode") != "0000":
        raise ValueError("Invalid energy response")
    records = response["result"]["dataList"]
    if not isinstance(records, list):
        raise ValueError("Invalid daily energy list")
    rows = {}
    for record in records:
        day = datetime.strptime(record["usedDate"], "%Y%m%d").date()
        wh = record["energyUsage"]
        if type(wh) is not int or wh < 0 or not first_day <= day <= last_day:
            raise ValueError("Invalid daily energy reading")
        if day in rows and rows[day] != wh:
            raise ValueError("Conflicting readings for the same day")
        rows[day] = wh
    return rows


class Metrics:
    def __init__(self, device):
        self.device = device
        self.state = ({}, {}, None, 0)
        self.energy_success = 0

    def collect(self):
        values, labels, last_success, success = self.state
        metrics = {
            **values,
            "state_collection_success": success,
            "energy_collection_success": self.energy_success,
        }
        if last_success is not None:
            metrics["state_last_success_timestamp_seconds"] = last_success
        for name, value in metrics.items():
            metric = GaugeMetricFamily(f"lg_thinq_{name}", name.replace("_", " "), labels=["device"])
            metric.add_metric([self.device], value)
            yield metric
        if labels:
            metric = GaugeMetricFamily(
                "lg_thinq_device_state_info", "State reported by LG",
                labels=["device", *labels],
            )
            metric.add_metric([self.device, *labels.values()], 1)
            yield metric


def report_failure(operation, error):
    code = error.code if isinstance(error, ThinQAPIException) else ""
    LOG.warning("%s failed: %s %s", operation, type(error).__name__, code)


async def poll_state(api, device_id, metrics):
    while True:
        try:
            state = await api.async_get_device_status(device_id)
            if not isinstance(state, dict) or not state:
                raise ValueError("Empty device state")
            values, labels = state_metrics(state)
            metrics.state = (values, labels, time.time(), 1)
        except Exception as error:
            values, labels, last_success, _ = metrics.state
            metrics.state = (values, labels, last_success, 0)
            report_failure("State collection", error)
        await asyncio.sleep(STATE_INTERVAL)


async def poll_energy(api, device_id, metrics, dsn):
    while True:
        try:
            last_day = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
            first_day = last_day - timedelta(days=6)
            response = await api.async_get_device_energy_usage(
                device_id, "energyUsage", USAGE_DAILY,
                first_day.strftime("%Y%m%d"), last_day.strftime("%Y%m%d"),
            )
            rows = energy_rows(response, first_day, last_day)
            if rows:
                async with await AsyncConnection.connect(dsn, connect_timeout=10) as connection:
                    async with connection.cursor() as cursor:
                        await cursor.executemany(
                            """
                            INSERT INTO public.lg_thinq_daily_energy (device, day, energy_wh)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (device, day) DO UPDATE
                            SET energy_wh = EXCLUDED.energy_wh
                            WHERE lg_thinq_daily_energy.energy_wh IS DISTINCT FROM EXCLUDED.energy_wh
                            """,
                            [(metrics.device, day, wh) for day, wh in rows.items()],
                        )
            metrics.energy_success = 1
        except Exception as error:
            metrics.energy_success = 0
            report_failure("Energy collection", error)
        await asyncio.sleep(ENERGY_INTERVAL)


async def main():
    device_id = os.environ["LG_THINQ_DEVICE_ID"].strip()
    token = os.environ["LG_THINQ_TOKEN"].strip()
    device = os.environ["LG_THINQ_DEVICE_NAME"].strip()
    if not all((device_id, token, device)):
        raise ValueError("Device name, device ID and token are required")
    dsn = os.environ.get("LG_THINQ_PG_DSN", "").strip()
    metrics = Metrics(device)
    registry = CollectorRegistry()
    registry.register(metrics)
    start_http_server(9810, registry=registry)

    client_id = str(uuid5(NAMESPACE_URL, f"lg-thinq-exporter:{device_id}"))
    async with ClientSession(timeout=ClientTimeout(total=20)) as session:
        api = ThinQApi(session, token, "BR", client_id)
        if dsn:
            await asyncio.gather(poll_state(api, device_id, metrics), poll_energy(api, device_id, metrics, dsn))
        else:
            LOG.info("Energy collection is disabled until the PostgreSQL Secret is configured")
            await poll_state(api, device_id, metrics)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

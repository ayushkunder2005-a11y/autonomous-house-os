"""Canonical MQTT fleet emulator for load and end-to-end integration tests."""

import argparse
import asyncio
import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

import aiomqtt


@dataclass
class Node:
    device_id: str
    room: str
    sequence: int = 0
    state: dict[str, Any] = field(default_factory=lambda: {"power": "OFF"})


class FleetEmulator:
    def __init__(self, house_id: str, node_count: int, telemetry_hz: float) -> None:
        self.house_id = house_id
        self.period = 1 / telemetry_hz
        self.nodes = [
            Node(f"esp32_sim_{index:03d}", f"room_{index % 8}") for index in range(node_count)
        ]

    async def run(self, host: str, port: int, username: str | None, password: str | None) -> None:
        async with aiomqtt.Client(
            hostname=host,
            port=port,
            username=username,
            password=password,
            identifier=f"house-fleet-emulator-{os.getpid()}",
        ) as client:
            await client.subscribe(f"house/{self.house_id}/command/+/+", qos=2)
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._telemetry_loop(client))
                tasks.create_task(self._heartbeat_loop(client))
                tasks.create_task(self._command_loop(client))

    async def _telemetry_loop(self, client: aiomqtt.Client) -> None:
        started = time.monotonic()
        while True:
            tick = time.monotonic() - started
            for index, node in enumerate(self.nodes):
                node.sequence += 1
                metric = "temperature" if index % 2 == 0 else "humidity"
                baseline = 24.0 if metric == "temperature" else 55.0
                value = baseline + math.sin(tick / 60 + index) + random.uniform(-0.05, 0.05)
                sensor_id = f"{metric}_{node.device_id}"
                topic = (
                    f"house/{self.house_id}/telemetry/ground/{node.room}/"
                    f"{node.device_id}/{sensor_id}"
                )
                payload = {
                    "timestamp": int(time.time() * 1000),
                    "sensor_id": sensor_id,
                    "device_id": node.device_id,
                    "metric_type": metric,
                    "value": round(value, 3),
                    "unit": "C" if metric == "temperature" else "%",
                    "read_seq": node.sequence,
                    "status": "VALID",
                    "battery_pct": None,
                }
                await client.publish(topic, json.dumps(payload), qos=1)
            await asyncio.sleep(self.period)

    async def _heartbeat_loop(self, client: aiomqtt.Client) -> None:
        while True:
            for node in self.nodes:
                await client.publish(
                    f"house/{self.house_id}/heartbeat/{node.device_id}",
                    json.dumps(
                        {
                            "device_id": node.device_id,
                            "status": "ONLINE",
                            "rssi_dbm": random.randint(-70, -45),
                            "uptime_seconds": int(time.monotonic()),
                            "free_heap_bytes": random.randint(170_000, 220_000),
                            "firmware_version": "emulator-1.0.0",
                        }
                    ),
                    qos=1,
                    retain=True,
                )
            await asyncio.sleep(10)

    async def _command_loop(self, client: aiomqtt.Client) -> None:
        by_id = {node.device_id: node for node in self.nodes}
        async for message in client.messages:
            parts = str(message.topic).split("/")
            if len(parts) != 5 or parts[2] != "command":
                continue
            command = json.loads(bytes(message.payload).decode())
            node = by_id.get(parts[3])
            if node is None:
                continue
            action = str(command["action"]).lower()
            if action == "turn_on":
                node.state["power"] = "ON"
            elif action == "turn_off":
                node.state["power"] = "OFF"
            else:
                node.state.update(command.get("parameters", {}))
            ack = {
                "command_id": command["command_id"],
                "device_id": node.device_id,
                "endpoint": command["endpoint"],
                "status": "APPLIED",
                "execution_duration_ms": random.uniform(3, 25),
                "current_state": node.state,
                "error_code": None,
            }
            await client.publish(
                f"house/{self.house_id}/ack/{node.device_id}/{command['command_id']}",
                json.dumps(ack),
                qos=2,
            )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Emulate a canonical House OS ESP32 fleet")
    parser.add_argument("--house-id", required=True)
    parser.add_argument("--nodes", type=int, default=50)
    parser.add_argument("--hz", type=float, default=10)
    parser.add_argument("--host", default=os.getenv("HOUSE_MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HOUSE_MQTT_PORT", "1883")))
    args = parser.parse_args()
    await FleetEmulator(args.house_id, args.nodes, args.hz).run(
        args.host,
        args.port,
        os.getenv("HOUSE_MQTT_USERNAME"),
        os.getenv("HOUSE_MQTT_PASSWORD"),
    )


if __name__ == "__main__":
    asyncio.run(main())

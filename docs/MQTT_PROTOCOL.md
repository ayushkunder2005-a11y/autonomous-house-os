# MQTT protocol implementation notes

The authoritative field contract is [Architecture Document 03](03_MQTT_AND_HARDWARE_PROTOCOL.md) and the machine-readable registry is [`contracts/mqtt_topics.json`](../contracts/mqtt_topics.json). The backend validates and implements those canonical topics without translation:

```text
house/{house_id}/telemetry/{floor}/{room}/{device_id}/{sensor_id}  QoS 1
house/{house_id}/command/{device_id}/{endpoint}                    QoS 2
house/{house_id}/state/{device_id}/{endpoint}                      QoS 1 retained
house/{house_id}/ack/{device_id}/{command_id}                      QoS 2
house/{house_id}/heartbeat/{device_id}                             QoS 1 retained
house/{house_id}/emergency/broadcast                               QoS 2
```

`DeviceService` validates telemetry, acknowledgements, and heartbeats with the authoritative Pydantic contracts. Publishing a command is never treated as success: a QoS-2 hardware ACK must report `APPLIED`, and its `current_state` must contain the expected values. Mismatch, local rejection, hardware timeout, or bounded server timeout results in a non-success command state.

The process-local simulation bus has identical topic matching and payload semantics. `simulation/esp32_fleet_emulator.py` provides broker-based 20+ node and stress-test operation. The PlatformIO firmware uses pinned FreeRTOS tasks, queues between networking and GPIO control, TLS certificate validation, QoS 1/2, a 15-second deadman, and fail-safe relay output.

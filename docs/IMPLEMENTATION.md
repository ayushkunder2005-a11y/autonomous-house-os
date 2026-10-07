# Implementation architecture

## Control path

```text
authenticated API / validated automation
  -> permission + house-scope check
  -> capability + deterministic safety validation
  -> persisted pending command and event
  -> canonical MQTT command dispatch (QoS 2)
  -> ESP32 accepted/rejected acknowledgement
  -> ESP32 applies hardware output
  -> ESP32 reports observed state with correlation ID
  -> backend reconciles observed state and completes only on a match
  -> state history + tamper-evident event + WebSocket broadcast
```

Publishing is never treated as success. A command that lacks acknowledgement or matching state is retried a bounded number of times and then failed while reducing device health.

## Runtime modes

With `HOUSE_MQTT_ENABLED=false`, `InMemoryBus` and `SimulatedDeviceManager` implement the exact `MessageBus` and canonical MQTT topic contract. With it enabled, `MQTTBus` uses `aiomqtt`, credential authentication, optional CA-validated TLS, automatic reconnect backoff, and contract QoS 1/2 subscriptions. Device records choose a `simulated` or `mqtt` driver; no API or automation changes are required when replacing a simulated device with hardware.

## Persistence

SQLAlchemy models cover houses, floors, rooms, users, roles, permissions, devices, sensors, state history, readings, commands, health, automations, scenes, events, security events, energy, water, maintenance, AI decisions, memory, experiments, and audit logs. SQLite is the local default and PostgreSQL is the deployment target. Alembic owns production schema changes.

JSON is limited to genuinely variable structures such as device capabilities/state, automation rule documents, provider metadata, and raw protocol payloads. Queryable ownership, timestamps, status, telemetry values, identities, and relationships remain relational.

## Trust boundaries

- JWT access tokens identify active users; roles grant explicit permissions and all house data is scope checked.
- Device control has no unauthenticated route.
- Unlock requires explicit confirmation and pumps, set points, brightness, and speed use deterministic limits.
- Smoke, gas, water leak, overheating, and abnormal electrical rules do not depend on AI availability.
- Natural-language providers return structured intent only. Execution requires a configured scene or automation, authorization, and the normal deterministic command pipeline.
- What-if simulation reads state and estimates effects but has no reference to the command service or message bus.
- The event black box uses a SHA-256 chain and offers an integrity-verification endpoint. Database access controls and backups remain necessary for operational tamper resistance.

## Extensibility

New devices supply capabilities and a driver without modifying API routes. New prediction models implement `PredictionProvider`; new intent services implement `IntentProvider`; new transports implement `MessageBus`. Deterministic automation conditions and actions remain independent from AI providers.

## Web console

The React/Vite console implements Anti Gravity's responsive obsidian cockpit, ten-domain navigation, live Digital Twin summary, spatial room cards, device diagnostics, token authentication, and the multiplexed WebSocket heartbeat/subscription contract. Domain-specific views remain deliberately driven by the existing API instead of duplicating automation logic in the browser.

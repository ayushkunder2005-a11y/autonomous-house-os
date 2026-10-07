# Autonomous House OS

A simulation-first FastAPI house-control backend with the same command and telemetry contracts used by real ESP32 nodes. The implementation keeps AI interpretation outside the hardware trust boundary: every command passes role authorization, capability validation, deterministic safety checks, acknowledgement handling, and reported-state verification.

## Run locally

Python 3.11+ is required. No Raspberry Pi is used.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
alembic upgrade head
python backend/scripts/create_admin.py admin@example.com
uvicorn app.main:app --app-dir backend --reload
```

Open `http://localhost:8000/docs`, authenticate with `POST /api/v1/auth/token`, authorize Swagger with the bearer token, then call `POST /api/v1/simulation/bootstrap`. The returned simulation house contains lights, fan, AC, curtains, a lock, smart plug, pump, energy meter, and environmental sensors. `POST /api/v1/simulation/{house_id}/tick` generates telemetry through the MQTT-compatible transport path.

For a disposable development admin, set `HOUSE_BOOTSTRAP_ADMIN_EMAIL` and `HOUSE_BOOTSTRAP_ADMIN_PASSWORD` in `.env`. Leave the password unset in normal deployments and use the interactive script.

## Validate

```powershell
ruff check backend
pytest -q
alembic upgrade head
```

The test suite covers authentication and permissions, relational persistence, MQTT topic delivery, command acknowledgements and state verification, bounded retry failure, automation conflict handling, deterministic safety rules, simulation isolation, anomaly detection, energy/water analytics, maintenance, memory retrieval, and event-chain integrity.

## Deployment

`docker-compose.yml` provides PostgreSQL, authenticated Mosquitto, migrations, and the API. Before starting it:

1. Copy `.env.example` to `.env` and set unique `POSTGRES_PASSWORD`, `HOUSE_SECRET_KEY`, `MQTT_USERNAME`, and `MQTT_PASSWORD` values.
2. Generate `infrastructure/mosquitto/passwd` with `mosquitto_passwd`; its backend credentials must match the environment.
3. Keep the broker on a trusted private network or configure the documented TLS listener before allowing ESP32 connections from another network.
4. Run `docker compose up --build`.

The production configuration rejects the development JWT secret, automatic schema creation, and unauthenticated MQTT configuration.

## Repository map

- `backend/app`: API, domain models, services, authorization, automation, MQTT, analytics, safety, simulation, and realtime delivery.
- `backend/migrations`: versioned database schema.
- `backend/tests`: unit and integrated API tests.
- `esp32`: PlatformIO reference firmware.
- `infrastructure/mosquitto`: broker authentication and ACL configuration.
- `docs`: protocol and implementation notes.
- `frontend`: responsive React/Vite control console implementing Anti Gravity's ten-view UX shell.

See [implementation architecture](docs/IMPLEMENTATION.md) and [MQTT protocol](docs/MQTT_PROTOCOL.md) for integration details.

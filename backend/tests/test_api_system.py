import time

from fastapi.testclient import TestClient


def test_health_ready_and_openapi(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/devices/{device_id}/command" in schema["paths"]
    assert "/api/v1/simulation/house" in schema["paths"]


def test_multiplexed_websocket_contract(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    token = admin_headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/api/v1/ws/live-stream?token={token}") as websocket:
        assert websocket.receive_json()["event"] == "CONNECTED"
        websocket.send_json({"action": "SUBSCRIBE", "channels": ["energy:live"]})
        assert websocket.receive_json() == {"event": "SUBSCRIBED", "channels": ["energy:live"]}


def test_bad_login_uses_consistent_error(client: TestClient):
    response = client.post(
        "/api/v1/auth/token", data={"username": "admin@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "http_401"
    assert response.headers["X-Request-ID"]


def test_simulation_inventory(client: TestClient, admin_headers: dict[str, str], simulation: dict):
    response = client.get(f"/api/v1/houses/{simulation['house_id']}/devices", headers=admin_headers)
    assert response.status_code == 200
    kinds = {device["device_type"] for device in response.json()}
    assert {"light", "fan", "ac", "smart_plug", "pump", "energy_meter"} <= kinds


def test_simulated_command_requires_reported_state(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    devices = client.get(
        f"/api/v1/houses/{simulation['house_id']}/devices", headers=admin_headers
    ).json()
    light = next(item for item in devices if item["device_type"] == "light")
    response = client.post(
        f"/api/v1/devices/{light['id']}/commands",
        headers=admin_headers,
        json={"action": "turn_on", "parameters": {}},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "completed"
    refreshed = client.get(
        f"/api/v1/houses/{simulation['house_id']}/devices", headers=admin_headers
    ).json()
    assert next(item for item in refreshed if item["id"] == light["id"])["state"]["power"] == "on"


def test_safety_boundary_rejects_unsafe_temperature(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    devices = client.get(
        f"/api/v1/houses/{simulation['house_id']}/devices", headers=admin_headers
    ).json()
    ac = next(item for item in devices if item["device_type"] == "ac")
    response = client.post(
        f"/api/v1/devices/{ac['id']}/commands",
        headers=admin_headers,
        json={"action": "set_temperature", "parameters": {"temperature": 10}},
    )
    assert response.status_code == 422
    assert "between 16 and 30" in response.json()["error"]["message"]


def test_unacknowledged_real_device_command_fails_with_bounded_retries(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    response = client.post(
        "/api/v1/devices",
        headers=admin_headers,
        json={
            "house_id": simulation["house_id"],
            "room_id": simulation["room_ids"][0],
            "name": "Unreachable Relay",
            "device_type": "light",
            "driver": "mqtt",
            "capabilities": ["power"],
        },
    )
    assert response.status_code == 201, response.text
    device_id = response.json()["id"]
    command = client.post(
        f"/api/v1/devices/{device_id}/commands",
        headers=admin_headers,
        json={"action": "turn_on", "parameters": {}},
    )
    assert command.status_code == 202
    deadline = time.monotonic() + 1
    result = {}
    while time.monotonic() < deadline:
        result = client.get(
            f"/api/v1/commands/{command.json()['id']}", headers=admin_headers
        ).json()
        if result["status"] == "failed":
            break
        time.sleep(0.03)
    assert result["status"] == "failed"
    assert result["attempt_count"] == 2


def test_role_permission_denies_viewer_control(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    email = "viewer@example.com"
    create = client.post(
        "/api/v1/auth/users",
        headers=admin_headers,
        json={
            "email": email,
            "display_name": "Viewer",
            "password": "Viewer-password-123!",
            "role": "viewer",
            "house_id": simulation["house_id"],
        },
    )
    assert create.status_code in {201, 409}
    token = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": "Viewer-password-123!"},
    ).json()["access_token"]
    response = client.post(
        f"/api/v1/devices/{simulation['device_ids'][0]}/commands",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "turn_on", "parameters": {}},
    )
    assert response.status_code == 403


def test_what_if_simulation_never_changes_hardware(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    before = client.get(
        f"/api/v1/houses/{simulation['house_id']}/devices", headers=admin_headers
    ).json()
    ac_before = next(item for item in before if item["device_type"] == "ac")
    response = client.post(
        "/api/v1/simulation/house",
        headers=admin_headers,
        json={"house_id": simulation["house_id"], "text": "Set all AC units to 22 C"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["simulation_only"] is True
    after = client.get(
        f"/api/v1/houses/{simulation['house_id']}/devices", headers=admin_headers
    ).json()
    ac_after = next(item for item in after if item["id"] == ac_before["id"])
    assert ac_after["state"] == ac_before["state"]


def test_telemetry_energy_water_health_and_memory(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    house_id = simulation["house_id"]
    assert (
        client.post(f"/api/v1/simulation/{house_id}/tick", headers=admin_headers).status_code == 200
    )
    assert (
        client.post(
            "/api/v1/energy/readings",
            headers=admin_headers,
            json={"house_id": house_id, "power_watts": 450, "energy_kwh": 0.45, "cost": 0.08},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/water/readings",
            headers=admin_headers,
            json={"house_id": house_id, "volume_liters": 12, "flow_lpm": 2, "leak_detected": True},
        ).status_code
        == 201
    )
    energy = client.get(f"/api/v1/houses/{house_id}/energy", headers=admin_headers).json()
    assert energy["energy_kwh"] >= 0.45
    water = client.get(f"/api/v1/houses/{house_id}/water", headers=admin_headers).json()
    assert water["leak_detected"] is True
    health = client.get(f"/api/v1/houses/{house_id}/health", headers=admin_headers).json()
    assert health["components"]["water"]["active_leak"] is True
    memory = client.post(
        "/api/v1/memory/search",
        headers=admin_headers,
        json={"house_id": house_id, "query": "water leak"},
    ).json()
    assert any("leak" in item["content"].lower() for item in memory["items"])


def test_intent_executes_only_configured_validated_scene(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    response = client.post(
        "/api/v1/intents",
        headers=admin_headers,
        json={
            "house_id": simulation["house_id"],
            "text": "Prepare the house for sleeping.",
            "execute": True,
        },
    )
    # A prior explicit user command creates a Tier-3 manual hold, which must
    # preempt this Tier-4 scene until the hold expires.
    assert response.status_code == 409, response.text
    assert response.json()["error"]["message"]["reason"] == "TIER_3_PREEMPTS_TIER_4"


def test_event_black_box_chain_is_valid(client: TestClient, admin_headers: dict[str, str]):
    response = client.get("/api/v1/audit/integrity", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"valid": True, "broken_event_id": None}


def test_authoritative_twin_and_security_contracts(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    time.sleep(1.1)
    twin = client.get("/api/v1/twin/state", headers=admin_headers)
    assert twin.status_code == 200, twin.text
    assert twin.json()["house_id"] == simulation["house_id"]
    mode = client.post(
        "/api/v1/security/mode/set",
        headers={**admin_headers, "X-House-Security-PIN": "2468"},
        json={"mode": "AWAY"},
    )
    assert mode.status_code == 200, mode.text
    assert mode.json()["mode"] == "AWAY"
    client.post(
        "/api/v1/security/mode/set",
        headers=admin_headers,
        json={"mode": "HOME"},
    )


def test_condition_based_maintenance_history(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    device_id = simulation["device_ids"][0]
    response = client.post(
        f"/api/v1/devices/{device_id}/maintenance",
        headers=admin_headers,
        json={
            "maintenance_type": "inspect_wiring",
            "status": "recommended",
            "operating_hours": 1200,
            "failure_count": 2,
            "health_score": 72,
        },
    )
    assert response.status_code == 201, response.text
    history = client.get(f"/api/v1/devices/{device_id}/maintenance", headers=admin_headers).json()
    assert history[0]["maintenance_type"] == "inspect_wiring"


def test_level_zero_emergency_preempts_manual_control(
    client: TestClient, admin_headers: dict[str, str], simulation: dict
):
    trigger = client.post(
        "/api/v1/emergency/trigger",
        headers=admin_headers,
        json={"hazard_type": "SMOKE_FIRE", "source_room": "Kitchen"},
    )
    assert trigger.status_code == 200, trigger.text
    blocked = client.post(
        f"/api/v1/devices/{simulation['device_ids'][0]}/command",
        headers=admin_headers,
        json={"endpoint": "relay", "action": "turn_on", "parameters": {}},
    )
    assert blocked.status_code == 409
    reset = client.post(
        "/api/v1/emergency/reset",
        headers={**admin_headers, "X-House-Security-PIN": "2468"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["mode"] == "HOME"

import pytest
from app.ai.intents import RulesIntentProvider
from app.analytics.anomaly import RobustAnomalyDetector
from app.automation.engine import AutomationEngine
from app.contracts import PriorityTier, SecurityMode
from app.devices.safety import SafetyValidator
from app.devices.service import state_contains
from app.engine.priority.arbitrator import PriorityArbitrator
from app.models.device import Device
from app.mqtt.bus import InMemoryBus
from app.mqtt.topics import command_topic, parse_topic, topic_matches
from app.safety.monitor import SafetyMonitor
from fastapi import HTTPException


def test_topic_contract_round_trip():
    topic = command_topic("h1", "d1", "relay")
    parsed = parse_topic(topic)
    assert parsed is not None
    assert (parsed.house_id, parsed.endpoint, parsed.device_id, parsed.kind) == (
        "h1",
        "relay",
        "d1",
        "command",
    )
    assert topic_matches("house/+/command/+/+", topic)
    assert parse_topic("unsafe/arbitrary/topic") is None


@pytest.mark.asyncio
async def test_in_memory_bus_wildcard_delivery():
    bus = InMemoryBus()
    messages = []

    async def handler(topic, payload):
        messages.append((topic, payload))

    await bus.subscribe("house/+/telemetry/+/+/+/+", handler)
    await bus.start()
    topic = "house/h/telemetry/f/r/d/s"
    assert await bus.publish(topic, {"value": 1})
    assert messages == [(topic, {"value": 1})]
    await bus.stop()


def test_deterministic_safety_validation():
    device = Device(
        house_id="h",
        name="AC",
        device_type="ac",
        capabilities=["power", "temperature"],
        state={},
        availability="online",
    )
    validator = SafetyValidator()
    assert validator.validate(device, "set_temperature", {"temperature": 24}).allowed
    assert not validator.validate(device, "set_temperature", {"temperature": 10}).allowed
    assert not validator.validate(device, "unlock", {}).allowed


def test_emergency_rules_do_not_depend_on_ai():
    monitor = SafetyMonitor()
    assert monitor.evaluate("smoke", 1).event_type == "emergency.smoke"
    assert monitor.evaluate("temperature", 66).event_type == "emergency.overheating"
    assert monitor.evaluate("temperature", 25) is None


def test_robust_anomaly_detection():
    detector = RobustAnomalyDetector()
    result = detector.detect([10, 10.1, 9.9, 10.2, 9.8, 10], 50)
    assert result.anomalous
    assert result.score > 3.5


def test_state_verification_is_subset_based():
    assert state_contains({"power": "on", "brightness": 20}, {"power": "on"})
    assert not state_contains({"power": "off"}, {"power": "on"})


def test_conflicting_automation_actions_are_rejected():
    with pytest.raises(HTTPException) as exc:
        AutomationEngine._validate_action_conflicts(
            [
                {"device_id": "d1", "action": "turn_on", "parameters": {}},
                {"device_id": "d1", "action": "turn_off", "parameters": {}},
            ]
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_intent_provider_only_returns_structured_intent():
    provider = RulesIntentProvider()
    intent = await provider.interpret("Prepare the house for sleeping.")
    assert intent.intent == "sleep_mode"
    assert intent.executable
    unsafe = await provider.interpret("Set the AC to 10 C")
    assert not unsafe.executable


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        return None


def device(kind="light", state=None, capabilities=None):
    return Device(
        id=f"{kind}-1",
        house_id="house-1",
        name=kind,
        device_type=kind,
        capabilities=capabilities or ["power"],
        state=state or {},
        availability="online",
    )


@pytest.mark.asyncio
async def test_priority_tiers_manual_hold_and_emergency_lock():
    db = FakeSession()
    arbitrator = PriorityArbitrator()
    light = device()
    manual = await arbitrator.evaluate(
        db,
        device=light,
        endpoint="relay",
        action="turn_on",
        parameters={},
        tier=PriorityTier.LEVEL_3_MANUAL_OVERRIDE,
        source="user",
    )
    assert manual.approved
    ai = await arbitrator.evaluate(
        db,
        device=light,
        endpoint="relay",
        action="turn_off",
        parameters={},
        tier=PriorityTier.LEVEL_5_AUTONOMOUS_OPTIMIZATION,
        source="ai",
    )
    assert not ai.approved and "TIER_3" in ai.reason
    emergency = await arbitrator.evaluate(
        db,
        device=light,
        endpoint="relay",
        action="force_off",
        parameters={},
        tier=PriorityTier.LEVEL_0_SAFETY_EMERGENCY,
        source="safety",
    )
    assert emergency.approved
    blocked = await arbitrator.evaluate(
        db,
        device=light,
        endpoint="relay",
        action="turn_on",
        parameters={},
        tier=PriorityTier.LEVEL_3_MANUAL_OVERRIDE,
        source="user",
    )
    assert blocked.reason == "LEVEL_0_EMERGENCY_LOCK"
    await arbitrator.clear_emergency()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "action", "parameters", "mode", "reason"),
    [
        (
            device("pump", {"tank_level_pct": 5}),
            "turn_on",
            {},
            SecurityMode.HOME,
            "PUMP_DRY_RUN_LOCKOUT",
        ),
        (device("lock", {}, ["lock"]), "unlock", {}, SecurityMode.AWAY, "SECURITY_MODE_LOCKOUT"),
        (
            device("ac", {"window_open_seconds": 181}, ["temperature"]),
            "set_parameters",
            {"mode": "COOL"},
            SecurityMode.HOME,
            "THERMAL_ENVELOPE_OPEN",
        ),
    ],
)
async def test_priority_physical_interlocks(target, action, parameters, mode, reason):
    decision = await PriorityArbitrator().evaluate(
        FakeSession(),
        device=target,
        endpoint="default",
        action=action,
        parameters=parameters,
        tier=PriorityTier.LEVEL_3_MANUAL_OVERRIDE,
        source="user",
        security_mode=mode,
    )
    assert not decision.approved
    assert decision.reason == reason


def test_safety_validator_edge_cases():
    validator = SafetyValidator()
    offline = device(state={})
    offline.availability = "offline"
    assert not validator.validate(offline, "turn_on", {}).allowed
    assert not validator.validate(device(), "invented", {}).allowed
    dimmer = device(capabilities=["brightness"])
    assert not validator.validate(dimmer, "set_brightness", {"brightness": 101}).allowed
    assert validator.validate(dimmer, "set_brightness", {"brightness": 50}).allowed
    lock = device("lock", capabilities=["lock"])
    assert not validator.validate(lock, "unlock", {}).allowed
    assert validator.validate(lock, "unlock", {"confirmed": True}).allowed
    pump = device("pump", {"dry_run_detected": True})
    assert not validator.validate(pump, "turn_on", {}).allowed


def test_additional_emergency_thresholds():
    monitor = SafetyMonitor()
    assert monitor.evaluate("gas", 1500).event_type == "emergency.gas"
    assert monitor.evaluate("power_w", 10_000).event_type == "emergency.electrical"

from dataclasses import dataclass

from app.automation.engine import AutomationEngine
from app.core.config import Settings
from app.database.session import SessionFactory
from app.devices.service import DeviceService
from app.mqtt.bus import InMemoryBus, MessageBus, MQTTBus
from app.recovery.reconciler import RecoveryReconciler
from app.security.modes import EmergencyService
from app.simulation.devices import SimulatedDeviceManager
from app.transport.redis_bus import RedisEventPipeline
from app.twin.state_manager import DigitalTwinStateManager


@dataclass
class Runtime:
    bus: MessageBus
    devices: DeviceService
    simulator: SimulatedDeviceManager
    automations: AutomationEngine
    twin: DigitalTwinStateManager
    emergency: EmergencyService
    events: RedisEventPipeline
    recovery: RecoveryReconciler

    @classmethod
    def build(cls, settings: Settings) -> "Runtime":
        bus: MessageBus = MQTTBus(settings) if settings.mqtt_enabled else InMemoryBus()
        events = RedisEventPipeline(settings.redis_url)
        emergency = EmergencyService(bus)
        devices = DeviceService(bus, SessionFactory, settings, events, emergency)
        simulator = SimulatedDeviceManager(bus, SessionFactory)
        automations = AutomationEngine(devices, SessionFactory, bus)
        twin = DigitalTwinStateManager(SessionFactory)
        recovery = RecoveryReconciler(bus, events)
        return cls(
            bus=bus,
            devices=devices,
            simulator=simulator,
            automations=automations,
            twin=twin,
            emergency=emergency,
            events=events,
            recovery=recovery,
        )

    async def start(self) -> None:
        await self.events.start()
        await self.bus.start()
        await self.recovery.start()
        await self.devices.start()
        await self.simulator.start()
        await self.automations.start()
        await self.twin.start()

    async def stop(self) -> None:
        await self.twin.stop()
        await self.automations.stop()
        await self.devices.stop()
        await self.recovery.stop()
        await self.bus.stop()
        await self.events.stop()

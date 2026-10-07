# ESP32 reference node

This PlatformIO firmware demonstrates the production protocol boundary for a relay-style device. Copy `include/secrets.h.example` to the ignored `include/secrets.h`, provision a unique MQTT account, identifiers, and CA certificate, then run `pio run`.

The node uses TLS, bounded exponential reconnection, a safe boot state, QoS 1 subscription, explicit accepted/rejected acknowledgements, state publication carrying the command correlation ID, and periodic health reports. Extend `handleCommand` and `publishState` for the actual hardware driver; do not remove acknowledgement plus reported-state verification.


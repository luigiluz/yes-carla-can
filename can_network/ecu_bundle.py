from can_network.bus_config import CAN_INTERFACE
from can_network.network import CAN_Network, SharedPhysicalBus


class ECUBundle:
    """The POWERTRAIN/COMFORT ECU pair for one script, plus their traffic displays if
    requested. Hides whether the two ECUs share one physical bus handle (neovi) or each
    opened their own (socketcan/vcan) — callers just use .powertrain/.comfort/.poll()/
    .shutdown() the same way either way.
    """

    def __init__(self, powertrain, comfort, poll_fn, shutdown_fn,
                 powertrain_display=None, comfort_display=None):
        self.powertrain = powertrain
        self.comfort = comfort
        self.powertrain_display = powertrain_display
        self.comfort_display = comfort_display
        self._poll_fn = poll_fn
        self._shutdown_fn = shutdown_fn

    def poll(self):
        self._poll_fn()

    def shutdown(self):
        self._shutdown_fn()


def open_ecu_bundle(dbc_path, powertrain_channel, comfort_channel, serial=None, with_displays=False):
    """Build the POWERTRAIN/COMFORT ECU pair for one script.

    On the neovi backend, a physical device can only be opened once per process, so both
    ECUs (and, if requested, both traffic-display panels) share a single SharedPhysicalBus
    handle. On socketcan/vcan, each ECU keeps opening its own bus independently — the
    kernel already lets multiple sockets attach to one interface, so no sharing is needed.
    """
    if CAN_INTERFACE == "neovi":
        shared = SharedPhysicalBus(powertrain_channel, comfort_channel, serial=serial)
        powertrain = CAN_Network(dbc_path, ecu_bus="POWERTRAIN", bus=shared.bus, send_channel=shared.powertrain_netid)
        comfort = CAN_Network(dbc_path, ecu_bus="COMFORT", bus=shared.bus, send_channel=shared.comfort_netid)
        shared.add_consumer(shared.powertrain_netid, powertrain._apply_frame)
        shared.add_consumer(shared.comfort_netid, comfort._apply_frame)

        powertrain_display = comfort_display = None
        if with_displays:
            from gui import CANTrafficDisplay
            powertrain_display = CANTrafficDisplay(channel=powertrain_channel, passive=True)
            comfort_display = CANTrafficDisplay(channel=comfort_channel, passive=True)
            shared.add_consumer(shared.powertrain_netid, powertrain_display.feed)
            shared.add_consumer(shared.comfort_netid, comfort_display.feed)

        def shutdown():
            shared.shutdown()
            if powertrain_display:
                powertrain_display.stop()
            if comfort_display:
                comfort_display.stop()

        return ECUBundle(powertrain, comfort, shared.poll, shutdown, powertrain_display, comfort_display)

    powertrain = CAN_Network(dbc_path, channel=powertrain_channel, serial=serial, ecu_bus="POWERTRAIN")
    comfort = CAN_Network(dbc_path, channel=comfort_channel, serial=serial, ecu_bus="COMFORT")

    powertrain_display = comfort_display = None
    if with_displays:
        from gui import CANTrafficDisplay
        powertrain_display = CANTrafficDisplay(channel=powertrain_channel, serial=serial)
        comfort_display = CANTrafficDisplay(channel=comfort_channel, serial=serial)

    def poll():
        powertrain.recv_msg()
        comfort.recv_msg()

    def shutdown():
        powertrain.bus.shutdown()
        comfort.bus.shutdown()
        if powertrain_display:
            powertrain_display.stop()
        if comfort_display:
            comfort_display.stop()

    return ECUBundle(powertrain, comfort, poll, shutdown, powertrain_display, comfort_display)

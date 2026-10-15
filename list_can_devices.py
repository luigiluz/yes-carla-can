"""List connected Intrepid CAN devices and their serial numbers.

Usage:
    python3 list_can_devices.py

The printed serial (e.g. V2C291) is what --can-serial expects on the other
node scripts (CARLA_client_module.py, vehicle_controls_module.py,
cyberattacks_module.py, intrusion_detection_module.py) when CAN_INTERFACE=neovi.
"""

try:
    import ics
except ImportError as ie:
    print(f"python-ics is not installed, cannot list Intrepid devices: {ie}")
    raise SystemExit(1)

from can.interfaces.ics_neovi.neovi_bus import NeoViBus


def main():
    devices = ics.find_devices()
    if not devices:
        print("No Intrepid devices found.")
        return
    for device in devices:
        print(f"{device.Name}  serial={NeoViBus.get_serial_number(device)}")


if __name__ == "__main__":
    main()

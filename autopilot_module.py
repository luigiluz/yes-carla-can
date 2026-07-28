import argparse
import logging
import os
import random
import sys
import time
from pathlib import Path

import carla

from can_network import VCAN_CHANNEL
from can_network.network import AUTOPILOT_TIMEOUT, CAN_Network


PROJECT_DIR = Path(__file__).resolve().parent
CONTROL_INTERVAL = 0.1


def load_behavior_agent():
    carla_dir = os.environ.get("CARLA_FOLDER_NAME", "carla-0-9-15")
    local_python_api = PROJECT_DIR / carla_dir / "PythonAPI" / "carla"
    if local_python_api.is_dir():
        sys.path.insert(0, str(local_python_api))

    try:
        from agents.navigation.behavior_agent import BehaviorAgent
    except ImportError as error:
        raise RuntimeError(
            "CARLA's agents package was not found. Install the repository with "
            "0_install_dependencies.sh or rebuild the client Docker image."
        ) from error
    return BehaviorAgent


def find_hero(world):
    for vehicle in world.get_actors().filter("vehicle.*"):
        if vehicle.attributes.get("role_name") == "hero":
            return vehicle
    return None


def set_random_destination(agent, vehicle, world):
    origin = vehicle.get_location()
    destinations = [
        spawn_point
        for spawn_point in world.get_map().get_spawn_points()
        if origin.distance(spawn_point.location) >= 20.0
    ]
    if not destinations:
        raise RuntimeError("The loaded map has no destination away from the hero vehicle.")
    agent.set_destination(random.choice(destinations).location)


def safe_stop_control():
    return carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0)


def run(args):
    behavior_agent_class = load_behavior_agent()
    client = carla.Client(args.host, args.port)
    client.set_timeout(10.0)
    can_network = CAN_Network(dbc_path=args.dbc, channel=args.vcan)

    agent = None
    hero_id = None
    was_active = False

    logging.info("waiting for CAN autopilot command and hero vehicle")
    try:
        while True:
            loop_started = time.monotonic()
            can_network.recv_msg()
            active = can_network.autopilot_active(AUTOPILOT_TIMEOUT)

            if active:
                try:
                    world = client.get_world()
                    hero = find_hero(world)
                    if hero is None:
                        agent = None
                        hero_id = None
                    else:
                        if agent is None or hero.id != hero_id:
                            agent = behavior_agent_class(hero, behavior="normal")
                            hero_id = hero.id
                            set_random_destination(agent, hero, world)
                            logging.info(
                                "CAN autopilot engaged for hero vehicle %s", hero.id
                            )
                        elif agent.done():
                            set_random_destination(agent, hero, world)

                        can_network.send_msg(agent.run_step())
                except RuntimeError as error:
                    logging.warning("autopilot will retry after CARLA error: %s", error)
                    agent = None
                    hero_id = None
            elif was_active:
                can_network.send_msg(safe_stop_control())
                agent = None
                hero_id = None
                logging.info("CAN autopilot disengaged; safe stop sent")

            was_active = active
            remaining = CONTROL_INTERVAL - (time.monotonic() - loop_started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        can_network.bus.shutdown()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="CARLA BehaviorAgent that publishes ego controls through CAN."
    )
    parser.add_argument("--host", default="127.0.0.1", help="CARLA server host")
    parser.add_argument("--port", default=2000, type=int, help="CARLA server port")
    parser.add_argument(
        "--dbc", default="data/carla.dbc", help="Path to the CAN DBC file"
    )
    parser.add_argument(
        "--vcan",
        default=VCAN_CHANNEL,
        help=f"Virtual CAN interface name (default: {VCAN_CHANNEL})",
    )
    return parser.parse_args(argv)


def main():
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    try:
        run(parse_args())
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError) as error:
        logging.error("%s", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

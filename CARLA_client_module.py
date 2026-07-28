#!/usr/bin/env python

# Copyright (c) 2019 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB).
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import print_function

import argparse
import glob
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys

try:
    sys.path.append(
        glob.glob(
            "../carla/dist/carla-*%d.%d-%s.egg"
            % (
                sys.version_info.major,
                sys.version_info.minor,
                "win-amd64" if os.name == "nt" else "linux-x86_64",
            )
        )[0]
    )
except IndexError:
    pass

import tkinter as tk

import carla
import pygame
import yaml

from can_network.network import CAN_Network, VCAN_CHANNEL
from gui import CANTrafficDisplay, HUD, KeyboardControl, World


PROJECT_DIR = Path(__file__).parent
CONFIG_PATH = PROJECT_DIR / "config" / "config.yaml"


def load_config(path=CONFIG_PATH):
    try:
        with Path(path).open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"Could not load config/config.yaml: {error}") from None

    expected_fields = {"map", "vehicle", "traffic", "pedestrians"}
    if not isinstance(config, dict) or set(config) != expected_fields:
        raise ValueError(
            "config/config.yaml must contain exactly 'map', 'vehicle', "
            "'traffic', and 'pedestrians'."
        )

    map_name = config["map"]
    vehicle_blueprint = config["vehicle"]
    if not isinstance(map_name, str) or not map_name.strip():
        raise ValueError(
            "The config/config.yaml 'map' value must be a non-empty string."
        )
    if (
        not isinstance(vehicle_blueprint, str)
        or not vehicle_blueprint.strip().startswith("vehicle.")
    ):
        raise ValueError(
            "The config/config.yaml 'vehicle' value must be an exact vehicle blueprint."
        )


    config["map"] = map_name.strip()
    config["vehicle"] = vehicle_blueprint.strip()
    return config

def start_traffic(args, config):
    cars = config["traffic"]["cars"] if config["traffic"]["enabled"] else 0
    pedestrians = (
        config["pedestrians"]["count"]
        if config["pedestrians"]["enabled"]
        else 0
    )
    if cars == 0 and pedestrians == 0:
        return None

    traffic_script = PROJECT_DIR / "generate_traffic.py"
    if not traffic_script.exists():
        carla_dir = os.environ.get("CARLA_FOLDER_NAME", "carla-0-9-15")
        traffic_script = (
            PROJECT_DIR / carla_dir / "PythonAPI" / "examples" / "generate_traffic.py"
        )
    if not traffic_script.exists():
        raise ValueError("CARLA's generate_traffic.py script was not found.")

    command = [
        sys.executable,
        "-u",
        str(traffic_script),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--number-of-vehicles",
        str(cars),
        "--number-of-walkers",
        str(pedestrians),
        "--safe",
    ]
    if not args.sync:
        command.append("--asynch")

    logging.info(
        "starting CARLA traffic generator: cars=%d pedestrians=%d",
        cars,
        pedestrians,
    )
    return subprocess.Popen(command)


def stop_traffic(process):
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)


def game_loop(args, config):
    pygame.init()
    pygame.font.init()

    root = tk.Tk()
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    root.destroy()
    print(f"width: {width}, height: {height}")

    world = None
    traffic_process = None
    original_settings = None
    can_bus = CAN_Network(channel=args.vcan)
    can_display = CANTrafficDisplay(channel=args.vcan)

    try:
        client = carla.Client(args.host, args.port)
        client.set_timeout(2000.0)

        logging.info("loading map %s", config["map"])
        sim_world = client.load_world(config["map"])

        # Disable rendering and set fixed time step
        world_settings = sim_world.get_settings()
        world_settings.no_rendering_mode = True  # Disable rendering
        # fps = 30
        # world_settings.fixed_delta_seconds = round(1/fps, 2) # Set FPS
        sim_world.apply_settings(world_settings)

        if args.sync:
            original_settings = sim_world.get_settings()
            settings = sim_world.get_settings()
            if not settings.synchronous_mode:
                settings.synchronous_mode = True
                settings.fixed_delta_seconds = 0.05
            sim_world.apply_settings(settings)

            traffic_manager = client.get_trafficmanager()
            traffic_manager.set_synchronous_mode(True)

        display = pygame.display.set_mode(
            (width / 2, height / 2), pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        display.fill((0, 0, 0))
        pygame.display.flip()

        hud = HUD(width / 2, height / 2)
        world = World(sim_world, hud, args, can_bus, config["vehicle"])
        logging.info("spawned vehicle %s", config["vehicle"])

        traffic_process = start_traffic(args, config)
        controller = KeyboardControl(world)

        if args.sync:
            sim_world.tick()
        else:
            sim_world.wait_for_tick()

        clock = pygame.time.Clock()
        while True:
            if args.sync:
                sim_world.tick()
            clock.tick_busy_loop(60)
            if controller.parse_events(client, world, clock, can_bus):
                return
            world.tick(clock)
            world.render(display)
            can_display.render(display)
            pygame.display.flip()

    finally:
        stop_traffic(traffic_process)

        # Stop CARLA sensor streams first so the server can close sessions cleanly
        # before any other teardown that might talk to the server or tear down the
        # CAN interface.
        if world is not None:
            try:
                world.destroy()
            except Exception:
                pass

        can_display.stop()
        can_bus.bus.shutdown()

        try:
            if original_settings:
                sim_world.apply_settings(original_settings)
        except Exception:
            pass

        try:
            if world and world.recording_enabled:
                client.stop_recorder()
        except Exception:
            pass

        pygame.quit()


def main():
    argparser = argparse.ArgumentParser(description="CARLA Manual Control Receiver Client")
    argparser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="debug",
        help="print debug information",
    )
    argparser.add_argument(
        "--host",
        metavar="H",
        default="127.0.0.1",
        help="IP of the host server (default: 127.0.0.1)",
    )
    argparser.add_argument(
        "-p",
        "--port",
        metavar="P",
        default=2000,
        type=int,
        help="TCP port to listen to (default: 2000)",
    )
    argparser.add_argument(
        "--res",
        metavar="WIDTHxHEIGHT",
        default="1280x720",
        help="window resolution (default: 1280x720)",
    )
    argparser.add_argument(
        "--rolename",
        metavar="NAME",
        default="hero",
        help='actor role name (default: "hero")',
    )
    argparser.add_argument(
        "--gamma",
        default=2.2,
        type=float,
        help="Gamma correction of the camera (default: 2.2)",
    )
    argparser.add_argument(
        "--sync", action="store_true", help="Activate synchronous mode execution"
    )
    argparser.add_argument(
        "--vcan",
        default=VCAN_CHANNEL,
        help=f"Virtual CAN interface name (default: {VCAN_CHANNEL})",
    )
    args = argparser.parse_args()

    args.width, args.height = [int(x) for x in args.res.split("x")]

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format="%(levelname)s: %(message)s", level=log_level)
    logging.info("listening to server %s:%s", args.host, args.port)

    print(__doc__)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        config = load_config()
        game_loop(args, config)
    except ValueError as error:
        logging.error("%s", error)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        print("\nCancelled by user. Bye!")


if __name__ == "__main__":
    main()

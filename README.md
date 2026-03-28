# Yes, CARLA CAN

**Yes, CARLA CAN** is an automotive cybersecurity experimentation platform that extends the [CARLA](https://carla.org/) driving simulator with a virtual [CAN bus](https://en.wikipedia.org/wiki/CAN_bus). It lets you run attack and defense experiments against a simulated vehicle network without any dedicated hardware.

---

## Architecture overview

The project architecture and its main modules are presented in the following figure:

<p align="center">
  <img src="images/yes-we-can-architecture.png" alt="Yes, CARLA CAN — architecture overview">
</p>

The platform is composed of the following modules:

- **Virtual CAN Bus (SocketCAN)** — a kernel-level virtual network interface (`vcan0`) that acts as the shared communication medium. All other modules connect to it to send or receive CAN frames, mimicking a real in-vehicle bus.
- **CAN DBC Network Configuration** — a DBC file (`data/carla.dbc`) that defines the message IDs, signal encoding, and transmission periods for the virtual network. It is the single source of truth for the CAN message schema used across all modules.
- **CARLA Client Module** (`CARLA_client_module.py`) — connects to the CARLA simulator server, spawns the ego vehicle, and attaches the sensors used in the simulation: collision, GNSS, IMU, lane invasion, and radar.
- **Vehicle Controls Module** (`vehicle_controls_module.py`) — captures keyboard inputs and translates them into CAN frames according to the DBC schema, publishing them onto `vcan0` to control the simulated vehicle.
- **Cyberattacks Module** (`cyberattacks_module.py`) — injects malicious CAN frames onto the bus. Supports Denial-of-Service (DoS) flooding and reverse-engineering-based feature spoofing (e.g. forcing hand brake or lights).
- **Intrusion Detection Module** (`intrusion_detection_module.py`) — listens to `vcan0` in real time and applies statistical detection algorithms to identify anomalous traffic patterns and raise alerts.

The network node modules (CARLA client, vehicle controls, cyberattacks and intrusion detection) run concurrently on a single machine, making experiments fully self-contained and reproducible. Each layer is also independently extensible — new attack types, detection algorithms, or vehicle configurations can be integrated by following the existing module structure.

The modules in execution will look like the ones in the following image:

<p align="center">
  <img src="images/running-platform.png" alt="Yes, CARLA CAN — platform running with all modules">
</p>

> **Screenshot suggestion:** A side-by-side screenshot showing the CARLA simulator window alongside a terminal running `candump vcan0` would effectively illustrate live CAN traffic tied to vehicle actions.

---

## Dependencies

Yes, CARLA CAN depends on the following software components:

| Dependency | Purpose |
|---|---|
| **conda / Miniconda** | Python virtual environment management |
| **Python 3.9** | Runtime (required by several libraries) |
| **Python packages** | Listed in `requirements.txt` (key ones: `carla 0.9.15`, `cantools`, `python-can`, `dash`, `matplotlib`, `scikit-learn`) |
| **CARLA 0.9.15** | Autonomous driving simulator (server) |
| **can-utils** (Linux) | Kernel modules and CLI tools for the virtual CAN interface (`vcan0`) |

However, you do **NOT** need to install these manually. We provide a shell script that ease the installation of the aforementioned dependencies.

### Installing dependencies

Run the install script once. It will handle everything, prompting you only if Miniconda is not yet present:

```bash
bash 0_install_dependencies.sh
```

What the script does:
1. Installs `can-utils` via `apt-get`.
2. Checks for `conda`; if absent, offers to download and install Miniconda automatically.
3. Creates the `n4s_env` conda environment with Python 3.9 (skips if it already exists).
4. Installs all Python packages from `requirements.txt` into `n4s_env`.
5. Downloads and extracts CARLA 0.9.15 into the `carla-0-9-15/` folder.

> **Screenshot suggestion:** A terminal recording (or screenshot) of the script running successfully, ending with the `"CARLA installed successfully!"` message, would be a useful reference for reproducibility.

> **Disclaimer:** All experiments were conducted on Ubuntu/Debian. Behaviour on Windows/WSL was not tested.

>
> | Script | Purpose |
> |---|---|
> | `0_install_dependencies.sh` | Installs system packages, Miniconda (optional), the conda environment, Python packages, and CARLA |
> | `1_up_environment.sh` | Starts CARLA, creates the virtual CAN bus, and launches all Python modules |
> | `2_down_environment.sh` | Gracefully stops all processes and removes the virtual CAN interface |

---

## Setting up the simulation environment

### Step 1 - Specifying the network messages

The major contribution of our work is to bring in-vehicle network (specifically CAN network) concepts alongside to the CARLA driving simulation. In this direction, we need to specify the network messages that are going to be changed in the network.

Since we are working with CAN network, we have used the industry standard CAN Database (DBC) file for specifying the messages parameters and messages periods.

An example of a DBC file is presented down below. In this file, you can specify the CAN ID of, the signal size and length, their scale and offset and also minimal and max values. Alongside, we use the concept of DBC attribute to define the custom attribute "GenMsgCycleTime" where we specify the periods of the messages. For more information regarding CAN DBC file syntax, see [CSS Electronics — CAN DBC File Explained](https://www.csselectronics.com/pages/can-dbc-file-database-intro).

We provide a ready-to-use DBC file in the `data/carla.dbc` path. Running the platform as-is will use this DBC file.

```text
VERSION "1.0"
...
BU_: ECU

BO_ 1536 THROTTLE: 4 ECU
 SG_ THROTTLE_signal : 0|8@1+ (1,0) [0|255] ""  ECU

BO_ 1537 BRAKE: 4 ECU
 SG_ BRAKE_signal : 0|8@1+ (1,0) [0|255] ""  ECU

BO_ 1538 STEER: 4 ECU
 SG_ STEER_signal : 0|8@1+ (1,0) [0|255] ""  ECU
...

BA_DEF_ BO_ "GenMsgCycleTime" INT 0 10000;

BA_DEF_DEF_ "GenMsgCycleTime" 0;

BA_ "GenMsgCycleTime" BO_ 1536 100;
BA_ "GenMsgCycleTime" BO_ 1537 100;
BA_ "GenMsgCycleTime" BO_ 1538 100;
...
```

Once the DBC file is properly defined, we can move to actually simulate the CAN network and the vehicle behavior.

### Step 2 — Bring the core modules up

Once dependencies are installed and the DBC file specified, a single script starts the core of the simulation:

```bash
bash 1_up_environment.sh
```

Internally, the script:
1. Launches the **CARLA simulator** in headless, low-quality mode (`-RenderOffScreen -quality_level=Low`) to minimise resource usage.
2. Creates the **virtual CAN bus** (`vcan0`) using the Linux kernel `vcan` module.
3. Waits 5 seconds for CARLA to initialise.
4. Starts the **CARLA client module** (`CARLA_client_module.py`) — spawns the ego vehicle and sensors.
5. Starts the **vehicle controls module** (`vehicle_controls_module.py`) — translates vehicle state into CAN frames and puts them on `vcan0`.

Once the script is fully executed, you can control the vehicle using the keyboard, see it moving and see the CAN network traffic.


To monitor CAN traffic in real time, open a separate terminal and run:

```bash
candump vcan0
```

<p align="center">
  <img src="images/carla_simulator_canbus.png" alt="CARLA simulator alongside candump CAN traffic">
</p>

### Step 3 — Bring the core modules down

When you are done, tear everything down cleanly:

```bash
bash 2_down_environment.sh
```

The script stops the vehicle controls module, then the CARLA client module (waiting up to 10 seconds for a clean exit before force-killing), then the CARLA server, and finally removes `vcan0` and unloads the `vcan` kernel module.

---

## Demonstrations

Since you already know how to use the core functionalities of the "Yes, CARLA CAN" platform, we can move on to the demonstrations of automotive cybersecurity concepts.

For this section, we assume that the environment is already up (`1_up_environment.sh` has been run).

### Hand brake spoofing attack

<!-- TODO: add screenshot of cyberattacks_module DoS output and candump showing the flood -->

### Fuzzy attack

<!-- TODO: add screenshot of cyberattacks_module injection output and the resulting vehicle state change in the CARLA window -->

### Intrusion Detection System (IDS)

<!-- TODO: add screenshot of intrusion_detection_module alert output while a DoS or injection is active -->

### Collecting network traffic

## Common issues

### Check if virtualCAN was properly set up

You can verify that the virtual CAN interface was created successfully:

```bash
ifconfig
```

`vcan0` should appear in the list of network interfaces:

<p align="center">
  <img src="images/ifconfig_vcan0.png" alt="ifconfig output showing vcan0">
</p>


### Vulkan configuration (if the simulator fails to start)

On some Ubuntu systems, CARLA may not start correctly due to graphics driver issues. Install and configure Vulkan to resolve this:

```bash
vkconfig
```

Select the configuration shown below:

<p align="center">
  <img src="images/vulkan_config_highlighted.png" alt="Vulkan configuration">
</p>

Close `vkconfig` and re-run `1_up_environment.sh`.

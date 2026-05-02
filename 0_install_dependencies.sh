#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"
CONDA_ENV_NAME="n4s_env"
PYTHON_VERSION="3.9"

echo "Installing \"Yes, CARLA CAN\" project dependencies..."

# ------------------------------------------------------------------
# 1. System packages
# ------------------------------------------------------------------
echo "Installing system packages..."
sudo apt-get install -y \
    can-utils \
    curl \
    wget \
    libvulkan1 \
    mesa-vulkan-drivers

# ------------------------------------------------------------------
# 2. Miniconda (optional)
# ------------------------------------------------------------------
if command -v conda &>/dev/null; then
    echo "conda is already installed ($(conda --version)). Skipping Miniconda installation."
else
    read -r -p "conda was not found. Install Miniconda now? [y/N] " response
    if [[ "${response,,}" == "y" ]]; then
        echo "Downloading Miniconda installer..."
        curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

        echo "Running Miniconda installer..."
        bash Miniconda3-latest-Linux-x86_64.sh -b -p "$HOME/miniconda3"
        rm Miniconda3-latest-Linux-x86_64.sh

        # Initialise conda for the current shell session
        eval "$("$HOME/miniconda3/bin/conda" shell.bash hook)"
        "$HOME/miniconda3/bin/conda" init bash
        echo "Miniconda installed. Restart your terminal or run: source ~/.bashrc"
    else
        echo "Skipping Miniconda installation. conda must be available to continue."
        echo "Install it manually from https://www.anaconda.com/docs/getting-started/miniconda/install/linux-install"
        exit 1
    fi
fi

# ------------------------------------------------------------------
# 3. Conda environment
# ------------------------------------------------------------------
if ! command -v conda &>/dev/null; then
    echo "conda not found in PATH. Attempting to load from default Miniconda location..."
    source "$HOME/miniconda3/etc/profile.d/conda.sh" || { echo "Failed to load conda. Please activate it manually and re-run."; exit 1; }
fi

echo "Accepting Anaconda Terms of Service for default channels..."
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
echo "Anaconda Terms of Service accepted."

if conda env list | grep -q "^${CONDA_ENV_NAME}"; then
    echo "Conda environment '${CONDA_ENV_NAME}' already exists. Skipping creation."
else
    echo "Creating conda environment '${CONDA_ENV_NAME}' with Python ${PYTHON_VERSION}..."
    conda create -y -n "${CONDA_ENV_NAME}" python="${PYTHON_VERSION}"
fi

echo "Installing Python dependencies into '${CONDA_ENV_NAME}'..."
conda run -n "${CONDA_ENV_NAME}" pip install -r requirements.txt

echo "Python environment ready. Activate it with:"
echo "    conda activate ${CONDA_ENV_NAME}"

# ------------------------------------------------------------------
# 4. CARLA
# ------------------------------------------------------------------
mkdir -p ${CARLA_FOLDER_NAME}
cd ${CARLA_FOLDER_NAME}

echo "Downloading CARLA..."
wget https://tiny.carla.org/carla-0-9-15-linux

echo "Extracting CARLA..."
tar -xzvf carla-0-9-15-linux

echo "CARLA installed successfully!"

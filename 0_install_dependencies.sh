#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"
CONDA_ENV_NAME="n4s_env"
PYTHON_VERSION="3.9"

echo "Installing \"Yes, CARLA CAN\" project dependencies..."

# ------------------------------------------------------------------
# 1. System packages
# ------------------------------------------------------------------
echo "Installing can-utils..."
sudo apt-get install -y can-utils

# ------------------------------------------------------------------
# 2. Conda environment
# ------------------------------------------------------------------
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
# 3. CARLA
# ------------------------------------------------------------------
mkdir -p ${CARLA_FOLDER_NAME}
cd ${CARLA_FOLDER_NAME}

echo "Downloading CARLA..."
wget https://tiny.carla.org/carla-0-9-15-linux

echo "Extracting CARLA..."
tar -xzvf carla-0-9-15-linux

echo "CARLA installed successfully!"

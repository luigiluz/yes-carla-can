#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"

echo "Installing "Yes, CARLA CAN" project dependencies..."

echo "Installing can-utils..."
sudo apt-get install -y can-utils

mkdir -p ${CARLA_FOLDER_NAME}
cd ${CARLA_FOLDER_NAME}

echo "Downloading CARLA..."
wget https://tiny.carla.org/carla-0-9-15-linux

echo "Extracting CARLA..."
tar -xzvf carla-0-9-15-linux

echo "CARLA installed successfully!"

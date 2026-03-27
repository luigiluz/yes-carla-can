#!/bin/bash

echo "Installing "Yes, CARLA CAN" project dependencies..."

echo "Installing can-utils..."
sudo apt-get install -y can-utils

mkdir -p carla
cd carla

echo "Downloading CARLA..."
wget https://tiny.carla.org/carla-0-9-15-linux

echo "Extracting CARLA..."
tar -xzvf carla-0-9-15-linux

echo "CARLA installed successfully!"

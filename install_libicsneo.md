
https://intrepidcs.com/the-easy-way-to-program-valuecan-4-in-python-using-raspberry-pi-linux/

https://cdn.intrepidcs.net/servd/

https://github.com/intrepidcs/libicsneo.git

sudo apt install build-essential ninja-build cmake libusb-1.0-0-dev libpcap-dev

mkdir -p build/_deps/icspb-build/protos
cd build && make

# /etc/udev/rules.d/99-intrepidcs.rules
SUBSYSTEM=="usb", ATTRS{idVendor}=="093c", MODE="0660", GROUP="plugdev"

ACTION=="add", SUBSYSTEMS=="usb", ATTRS{idVendor}=="093c", KERNEL=="ttyUSB*", RUN+="/bin/sh -c 'echo $id:1.0>/sys/bus/usb/drivers/ftdi_sio/unbind'"

ACTION=="add", SUBSYSTEMS=="usb", ATTRS{idVendor}=="093c", DRIVER=="usbhid", RUN+="/bin/sh -c 'echo $id:1.0>/sys/bus/usb/drivers/usbhid/unbind'"


sudo udevadm control --reload-rules
sudo udevadm trigger

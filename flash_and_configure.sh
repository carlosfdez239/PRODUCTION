#!/bin/bash

# Function to display colored text
function echo_colored {
  local color="$1"
  local message="$2"
  local reset_color='\033[0m' # No Color
  echo -e "${color}${message}${reset_color}"
}

# Color codes
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Check for the device argument
if [ $# -ne 1 ]; then
  echo_colored "$BLUE" "Usage: $0 <device>"
  exit 1
fi

device="$1"

case "$device" in
  "VIB")
    firmware_file="FW-V3.15-VIB.bin"
    ;;
  "TIL")
    firmware_file="FW-V3.9-TILT360.bin"
    ;;
  "VW")
    firmware_file="app/VW_PCA_Test_v20250221.bin"
    ;;
  "GNSS")
    firmware_file="app/gnss_pca_v20250221.bin"
    ;;
  *)
    echo_colored "$BLUE" "Invalid device argument. Supported devices: LSG7ACL-BILH-VIB, LSG7ACL-BILR-TIL"
    exit 1
    ;;
esac

echo_colored "$YELLOW" "\nPaso 1. Descargando la aplicación a través del bootloader."
sleep 1
python3 lib/ls_updater.py --port=/dev/ttyUSB0 --file="$firmware_file"
sleep 1
echo_colored "$YELLOW" "Esperando..."
sleep 5
gtkterm --port=/dev/ttyUSB0 --speed=115200 > /dev/null 2>&1 &
sleep 2
xdotool search --name "gtkterm" windowminimize %@
echo_colored "$YELLOW" "Paso 3. Desconecte el cable USB-C del nodo. Luego, vuelva a conectarlo."
# Main script
read -n 1 -s -r -p "Presione una tecla para continuar..."

echo_colored "$YELLOW" "\nEsperando a que el nodo se reinicie.."
sleep 4
#echo_colored "$YELLOW" "Paso 4. Estableciendo el ID del Nodo y el ID del Producto para $device."
sleep 1
#./lib/configure_device.sh "$device"
#sleep 1
pkill gtkterm
sleep 1
read -n 1 -s -r -p "Presione una tecla para terminar..."

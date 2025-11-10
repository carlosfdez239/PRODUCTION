#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import threading
import time

import serial

# ANSI escape codes for text colors
RED = "\033[31m"
GREEN = "\033[32m"
BLUE = "\033[34m"
BRAND_BLUE = "\033[38;5;33m"
LIGHT_BLUE = "\033[38;5;117m"
YELLOW = "\033[33m"
RESET = "\033[0m"  # Reset color back to default


class LoadSensingFirmwareUpdater:
    """
    Helper class for flashing a node through the bootloader.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200):
        """
        Initialize the SerialFlashHelper.

        Args:
            port (str): The serial port to use.
            baudrate (int): The baudrate for the serial communication.
        """
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.receive_thread = None
        self.receive = False
        self.bootloader_present = False
        self.bootmenu_active = False
        self.lock = threading.Lock()
        self.has_error = False
        self.attempts = 0

    def set_error(self):
        with self.lock:
            self.has_error = True

    def get_error(self):
        with self.lock:
            return self.has_error

    def set_bootloader_present(self, val: bool):
        """
        Set the bootloader presence status.

        Args:
            val (bool): True if the bootloader is present, False otherwise.
        """
        with self.lock:
            self.bootloader_present = val

    def get_bootloader_present(self) -> bool:
        """
        Get the bootloader presence status.

        Returns:
            bool: True if the bootloader is present, False otherwise.
        """
        with self.lock:
            return self.bootloader_present

    def set_bootmenu_active(self, val: bool):
        """
        Set the bootmenu activation status.

        Args:
            val (bool): True if the bootmenu is active, False otherwise.
        """
        with self.lock:
            self.bootmenu_active = val

    def get_bootmenu_active(self) -> bool:
        """
        Get the bootmenu activation status.

        Returns:
            bool: True if the bootmenu is active, False otherwise.
        """
        with self.lock:
            return self.bootmenu_active

    def receive_handler(self):
        """
        Receive handler for monitoring serial input.
        """
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=5)
            while self.receive:
                if self.ser.in_waiting > 0:
                    try:
                        line = self.ser.readline().decode("utf-8")
                    except UnicodeDecodeError:
                        line = ""
                        continue

                    if "STM32 SBSFU Bootloader" in line:
                        self.set_bootloader_present(True)
                        print(
                            f"\r\nNode on {YELLOW}{self.port}{RESET}: Bootloader"
                            + GREEN
                            + " FOUND!"
                            + RESET
                        )
                    if "Download NonSecure App Image" in line:
                        self.set_bootmenu_active(True)
                    print(LIGHT_BLUE + line + RESET, end="")
        except serial.SerialException:
            print(f"\nSerial port error, please connect node.")
            print(f"{RED}DFU failed.{RESET}")
            self.set_error()
            sys.exit(1)

    def reboot_node(self):
        """
        Reboot the node and prepare for flashing.
        """
        print(f"\rNode reboot attempt {self.attempts}", end="")
        if self.ser is not None:
            msg = self.create_message("\x09")
            self.ser.write(msg)

        self.attempts += 1
        if self.attempts > 10:
            self.set_error()

        self.receive = True

    def create_message(self, msg: str):
        """Send message in correct byte format."""
        start_bytes = b"\x10\x02"
        end_bytes = b"\x10\x03"

        msg_bytes = msg.encode()
        modified_msg = msg_bytes.replace(b"\x10", b"\x10\x10")

        message_bytes = start_bytes + modified_msg + end_bytes

        return message_bytes

    def download_nonsecure_app(self, file_name: str):
        """
        Download and flash the NonSecure App.

        Args:
            file_name (str): The name of the application binaries to flash.
        """
        try:
            counter = 0
            print("Checking if there is a bootloader without application")
            while not self.get_bootmenu_active():
                if counter >= 30:
                    counter = 0
                    break
                counter += 1
                time.sleep(0.1)

            if not self.get_bootmenu_active():
                print("Application found on device.")
                counter = 0
                while not self.get_bootloader_present():
                    if self.get_error():
                        sys.exit(1)

                    if counter >= 10:
                        counter = 0
                        self.reboot_node()
                    time.sleep(0.25)
                    counter += 1

                print("Entering bootmenu..", end="")
                self.ser.write("worldsensing".encode("UTF-8"))
                counter = 0
                while not self.get_bootmenu_active():
                    if counter >= 20:
                        counter = 0
                        break

                    counter += 1
                    time.sleep(0.1)

            print("Selected" + YELLOW + " Download NonSecure App Image" + RESET)
            self.ser.write("3".encode("UTF-8"))  # select option "3" for NonSecure App
            self.receive = False

            if not file_name:
                print(
                    f"No filename given, searching for {BLUE}LoadSensingG_App{RESET} on machine... ",
                    end="",
                )
                loadsensing_dir = find_load_sensing_app_dir("/")
                print(GREEN + "Project found!" + RESET)
                print(f"Searching for {YELLOW}ns_app_enc_sign.bin {RESET}in {loadsensing_dir}")
                file_name = find_file_in_directory(loadsensing_dir, "ns_app_enc_sign.bin")
                print(f"Binaries {GREEN}FOUND!{RESET}")
            else:
                file = os.path.basename(file_name)
                print(f"Binaries {YELLOW}{file}{RESET} to be uploaded.")

            print("Starting file upload")
            print("====================================")
            flash_file_over_serial(file_name, self.port)

        except serial.SerialException as e:
            print(f"Serial port error: {e}")
            return


def find_load_sensing_app_dir(root_dir: str) -> str:
    """
    Find the directory of the LoadSensingG_App.

    Args:
        root_dir (str): The root directory to search in.

    Returns:
        str: The directory path if found, otherwise None.
    """
    for root, dirs, _ in os.walk(root_dir):
        if "LoadSensingG_App" in dirs:
            return os.path.join(root, "LoadSensingG_App")
    return None


def find_file_in_directory(directory: str, target_filename: str) -> str:
    """
    Find a file in a directory.

    Args:
        directory (str): The directory to search in.
        target_filename (str): The name of the file to find.

    Returns:
        str: The file path if found, otherwise None.
    """
    for root, _, files in os.walk(directory):
        if target_filename in files:
            return os.path.join(root, target_filename)
    return None


def flash_file_over_serial(file_path: str, serial_port: str):
    """
    Flash a file over a serial port.

    Args:
        file_path (str): The path to the file to flash.
        serial_port (str): The serial port to use.
    """
    try:
        command = f"sx --ymodem {file_path} < {serial_port} > {serial_port}"
        with subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True
        ) as p:
            for line in p.stdout:
                print(line, end="")

        if p.returncode == 0:
            print(f"{GREEN}DFU completed successfully.{RESET}")
        else:
            print(f"Error: Command exited with status {p.returncode}")

    except Exception as e:
        print(f"An error occurred: {e}")


def main():
    parser = argparse.ArgumentParser(description="Flash a node through the bootloader")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port to use")
    parser.add_argument(
        "--file", type=str, default="", help="Application binaries to flash to node"
    )
    args = parser.parse_args()

    abs_path = "FW-V3.9-TILT360.bin"
    if args.file != "":
        abs_path = os.path.abspath(args.file)
    print("")
    print("========================================")
    print("")
    print(f"{BRAND_BLUE}Loadsensing DFU Tool{RESET}")
    print("")
    print("========================================")
    lsfu = LoadSensingFirmwareUpdater(port=args.port)
    lsfu.receive_thread = threading.Thread(target=lsfu.receive_handler)
    lsfu.receive_thread.daemon = True
    lsfu.receive_thread.start()
    lsfu.reboot_node()
    lsfu.download_nonsecure_app(abs_path)


if __name__ == "__main__":
    main()

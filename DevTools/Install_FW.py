#!/usr/bin/env python3
import sys
import time
import serial
import subprocess
import pty
import os

def enviar_comandos(ser):
    print("Mandando \\nTEST_REBOOT")
    ser.write(b"TEST_REBOOT")
    try:
        respuesta = ser.read(ser.in_waiting or 64)
        print(f"Esperando al bootloader: {respuesta.decode('utf-8', errors='replace')}")
    except serial.SerialTimeoutException:
        print("Tiempo de espera agotado al leer del dispositivo.")
        return
    except serial.SerialException as e:
        print(f"Error de comunicación con el dispositivo: {e}")
        return
    time.sleep(0.2)

    print("writing")
    ser.write(b"worldsensing")
    #ser.flush()
    #time.sleep(0.2)
    print("Esperando al menu de entrada...")
    try:
        respuesta = ser.read(ser.in_waiting or 64)
        print(f"bootloader cargado --> Respuesta del dispositivo: {respuesta.decode('utf-8', errors='replace')}")
    except serial.SerialTimeoutException:
        print("Tiempo de espera agotado al leer del dispositivo.")
    except serial.SerialException as e:
        print(f"Error de comunicación con el dispositivo: {e}")
        return
    time.sleep(0.7)
    ser.write(b"3")
    try:
        respuesta = ser.read(ser.in_waiting or 64)
        print(f"Esperando a la opcion nº3: {respuesta.decode('utf-8', errors='replace')}")
    except serial.SerialTimeoutException:
        print("Tiempo de espera agotado al leer del dispositivo.")
    except serial.SerialException as e:
        print(f"Error de comunicación con el dispositivo: {e}")
        return
    time.sleep(1)
    ser.flush()

def enviar_ymodem(usb_path, binary_file_path):
    print("Iniciando envío por YMODEM...")

    # Crear pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Abrir el puerto serie real
    with open(usb_path, 'rb+', buffering=0) as serial_dev:
        try:
            # Lanzar sx con la pty esclava
            proc = subprocess.Popen(
                ["sx", "-vv", "--ymodem", binary_file_path],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=subprocess.STDOUT
            )

            # Redirigir tráfico entre el puerto serie y la pty
            while proc.poll() is None:
                try:
                    data = os.read(master_fd, 1024)
                    if data:
                        serial_dev.write(data)
                        serial_dev.flush()
                except BlockingIOError:
                    continue
        except Exception as e:
            print(f"Fallo durante la transferencia YMODEM: {e}")
        finally:
            os.close(master_fd)
            os.close(slave_fd)

def main():
    if len(sys.argv) != 3:
        print("Uso: python3 flash_firmware.py <usbPath> <binaryFilePath>")
        sys.exit(1)

    usb_path = sys.argv[1]
    binary_file_path = sys.argv[2]

    print(f"Usando puerto: {usb_path}")
    print(f"Archivo binario: {binary_file_path}")

    time.sleep(2)

    try:
        ser = serial.Serial(
            port=usb_path,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
    except serial.SerialException as e:
        print(f"Error al abrir el puerto serie: {e}")
        sys.exit(1)

    try:
        enviar_comandos(ser)
    except Exception as e:
        print(f"Error durante la comunicación previa: {e}")
        ser.close()
        sys.exit(1)

    ser.close()

    enviar_ymodem(usb_path, binary_file_path)


if __name__ == "__main__":
    main()

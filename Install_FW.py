'''
Script para instalar firmware en un dispositivo a través de YMODEM usando el comando `sx`.
Este script utiliza la biblioteca `serial` para manejar la comunicación serie
la placa debe llegar con PCA test instalado

Creado: Carlos Fdez
Fecha: 21/06/2025
revision: 2.0

To do

    [] Añadir manejo de errores más robusto.
    [] Añadir opciones de configuración para el puerto serie y el archivo binario.
    [] Implementar salida en pantalla más detallada para el proceso de transferencia.

Control de versiones:
 Version 1.0 - 21/06/2025
   - Versión inicial del script para la transferencia de firmware usando YMODEM.
 Versión 2.0 - 05/08/2025
    - Se modifica el tiempo de espera de 0,7 a 0,3 para la entrada al menú de bootloader.
    - Se incrementa a 1024 el reading del puerto serie, se añade el control de la salida del 
    terminal para evaluar FW correctamente grabado -->
        while True:
       try:
           data = ser.read(1024).decode('utf-8', errors='ignore')
           if data:
               print(f'output de la terminal --> {data}')
               if "Image correctly downloaded" in data:
                    print(f"✅ ✅ Transferencia YMODEM finalizada correctamente.")
                    break

'''


import serial
import time
import threading
import pty
import os
import subprocess
import sys

def read_from_port(ser):
    """Lee continuamente del puerto serie y muestra por pantalla."""
    while True:
        try:
            data = ser.read(1024)
            if data:
                print(data.decode(errors='ignore'), end='', flush=True)
            else:
                time.sleep(0.01)
        except Exception as e:
            print(f"Error leyendo puerto serie: {e}")
            break

def proxy_data(src_fd, dst_ser):
    """Lee del fd src y escribe en el puerto serie dst_ser."""
    while True:
        try:
            data = os.read(src_fd, 1024)
            if data:
                dst_ser.write(data)
                dst_ser.flush()
            else:
                time.sleep(0.01)
        except Exception as e:
            # Puede cerrar el hilo cuando no haya más datos
            break

def proxy_data_reverse(dst_fd, src_ser):
    """Lee del puerto serie src_ser y escribe en fd dst_fd."""
    while True:
        try:
            data = src_ser.read(1024)
            if data:
                os.write(dst_fd, data)
            else:
                time.sleep(0.01)
        except Exception as e:
            break


def crear_pty(binary_file, ser):
    # Crear pty para conectar sx con puerto serie real
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    print(f"PTY slave creado en: {slave_name}")

    # Lanzar sx conectado al pty slave
    sx_cmd = ["sx", "--ymodem", binary_file]
    print(f"Lanzando: {' '.join(sx_cmd)}")

    # Abrimos el slave_fd como archivo para pasar stdin/stdout a sx
    with os.fdopen(slave_fd, 'rb+', buffering=0) as slave_file:
        proc = subprocess.Popen(sx_cmd, stdin=slave_file, stdout=slave_file, stderr=subprocess.PIPE)

        # Proxy bidireccional entre pty master y puerto serie
        t1 = threading.Thread(target=proxy_data, args=(master_fd, ser), daemon=True)
        t2 = threading.Thread(target=proxy_data_reverse, args=(master_fd, ser), daemon=True)
        t1.start()
        t2.start()

        # Esperar que sx termine
        proc.wait()

def main():
    usb_path = "/dev/ttyUSB0"
    #binary_file = "/home/carlos/Documentos/G7/PRODUCTION/FW-V3.3-DYN.bin"
    #binary_file = "/home/carlos/Documentos/G7/PRODUCTION/tilt360_pca_v20250221.bin"
    binary_file = "FW-V3.15-VIB.bin"
    # Abrir puerto serie
    ser = serial.Serial(usb_path, 115200, timeout=0.5)

    # Arrancar hilo que lee puerto serie y muestra TODO lo que llegue (información del bootloader, logs, etc)
    lector_thread = threading.Thread(target=read_from_port, args=(ser,), daemon=True)
    lector_thread.start()

    # Enviar comandos iniciales con pausas
    #print("Mandando TEST_REBOOT")
    #ser.write("echo -e '\nTEST_REBOOT\n'".encode('utf-8', errors='ignore'))
    #ser.flush()
    time.sleep(0.7)

    print("writing")
    ser.write(b"worldsensing")
    #ser.flush()
    time.sleep(0.3)

    ser.write(b"3")
    #ser.flush()
    time.sleep(1)

    archivo_size = os.path.getsize(binary_file)
    print(f"\n📦 Enviando {archivo_size} bytes vía YMODEM...\n")
    #crear_pty(binary_file, ser)

    # Ejecutar el comando de transferencia YMODEM usando subprocess
    cmd = f'sx -v --ymodem {binary_file} < {usb_path} > {usb_path}'
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    while True:
       try:
           data = ser.read(1024).decode('utf-8', errors='ignore')
           if data:
               print(f'output de la terminal --> {data}')
               if "Image correctly downloaded" in data:
                    print(f"✅ ✅ Transferencia YMODEM finalizada correctamente.\n\n")
                    break
                   
       except Exception as e:
           break

    # Cerrar puerto serie
    ser.close()

if __name__ == "__main__":
    main()

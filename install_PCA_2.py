
import serial
import time
import threading
import subprocess
import sys

# --- Variables Globales y Configurables ---
BAUDRATE = 115200


# =======================
#  HILO LECTOR
# =======================
def read_from_port(ser, stop_event):
    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    print(data.decode(errors='ignore'), end='', flush=True)
            else:
                time.sleep(0.01) 
        except:
            break


# =======================
#  TRANSFERENCIA YMODEM
# =======================
def transferir_ymodem_directo(binary_file, usb_path):
    """
    Ejecuta YMODEM directamente sobre /dev/ttyUSB0 usando sx,
    sin PTY ni proxys. Esto garantiza funcionamiento correcto.
    """
    print("\n--- INICIANDO TRANSFERENCIA YMODEM (DIRECTO) ---")

    sx_cmd = [
        "sx",
        "-vvv",
        "--ymodem",
        binary_file
    ]

    print(f"Lanzando: {' '.join(sx_cmd)} sobre {usb_path}")

    try:
        # Abrimos el puerto en modo "raw" para stdin y stdout del proceso sx
        with open(usb_path, "rb", buffering=0) as ser_in, \
             open(usb_path, "wb", buffering=0) as ser_out:

            proc = subprocess.Popen(
                sx_cmd,
                stdin=ser_in,
                stdout=ser_out,
                stderr=subprocess.PIPE
            )

            proc.wait()

            stderr_output = proc.stderr.read().decode('utf-8', errors='ignore')

            if proc.returncode != 0:
                print(f"\n[ERROR] sx terminó con código {proc.returncode}")
                print(stderr_output)
                return False

            print("\n[ÉXITO] Transferencia YMODEM completada correctamente.")
            return True

    except Exception as e:
        print(f"[ERROR] Excepción durante transferencia directa: {e}")
        return False


# =======================
#  PROCESO PRINCIPAL
# =======================
def launch_fw_process(usb_path, binary_file):

    ser = None
    lector_thread = None
    stop_event = threading.Event()

    print("--- INICIO DEL PROCESO DE CARGA DE FIRMWARE ---")
    print(f'Puerto USB: {usb_path}, Archivo: {binary_file}')

    try:
        # 1. Abrir puerto serie
        ser = serial.Serial(usb_path, BAUDRATE, timeout=0.5)
        print(f"Puerto {usb_path} abierto a {BAUDRATE} baudios.")

        # 2. Iniciar lector
        lector_thread = threading.Thread(
            target=read_from_port, args=(ser, stop_event), daemon=True
        )
        lector_thread.start()
        print("Hilo lector iniciado.")

        # 3. Comandos de handshake
        print("Mandando comandos iniciales (TEST_REBOOT, worldsensing, 3)...")

        #ser.write(b"TEST_REBOOT\n")
        time.sleep(0.7)

        ser.write(b"worldsensing")
        time.sleep(0.2)

        ser.write(b"3")
        time.sleep(1)

        # 4. DETENER HILO LECTOR antes del YMODEM
        print("\nDeteniendo hilo lector para iniciar YMODEM...")
        stop_event.set()
        lector_thread.join(timeout=2)
        print("Hilo lector detenido.\n")

        # 5. Ejecutar transferencia YMODEM
        ymodem_success = transferir_ymodem_directo(binary_file, usb_path)

        if not ymodem_success:
            raise ValueError("La transferencia YMODEM falló.")

        # 6. REACTIVAR LECTOR DESPUÉS DEL YMODEM
        stop_event.clear()
        lector_thread = threading.Thread(
            target=read_from_port, args=(ser, stop_event), daemon=True
        )
        lector_thread.start()
        print("\nHilo lector reactivado. Esperando confirmación del bootloader...\n")

        # 7. Esperar confirmación final del bootloader
        start_time = time.time()
        timeout_seconds = 10

        while time.time() - start_time < timeout_seconds:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode(errors='ignore')
                if "App Image correctly downloaded" in data:
                    print("[ÉXITO] Confirmación de descarga recibida.")
                    break
            time.sleep(0.1)
        else:
            print("[ADVERTENCIA] No se recibió la confirmación final del bootloader.")

    except Exception as e:
        print(f"\n[ERROR FATAL] {e}")

    finally:
        print("\n--- FINALIZANDO PROCESO Y LIMPIEZA ---")

        stop_event.set()
        if lector_thread and lector_thread.is_alive():
            lector_thread.join(timeout=2)

        if ser and ser.is_open:
            ser.close()

        print("Proceso terminado.\n")


# =======================
#  MAIN
# =======================
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == "launch_fw_process":
        launch_fw_process(*sys.argv[2:])
    else:
        print("Uso:")
        print("  python3 install_PCA_2.py launch_fw_process /dev/ttyUSB0 firmware.bin")

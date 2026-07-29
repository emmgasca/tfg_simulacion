import asyncio
import struct
import sys
import time
import pandas as pd
from bleak import BleakClient
from protocolo_emg import desempaquetar_emg
from protocolo_eventos import desempaquetar_evento

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
CARACTERISTICA_IMU = "CCCCCCCC-1234-1234-1234-123456789ABC"
CARACTERISTICA_EVENTOS = "EEEEEEEE-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

NOMBRE_EVENTO = {0: "START", 1: "STOP", 2: "MARK"}

# Uso: python guardar.py [nombre] [duracion_s]
# -> guarda en <nombre>_emg.parquet / <nombre>_imu.parquet / <nombre>_eventos.parquet,
#    escuchando duracion_s segundos.
# Sin argumentos: nombre "captura", duracion 60s (como antes).
prefijo = sys.argv[1] if len(sys.argv) > 1 else "captura"
duracion_s = int(sys.argv[2]) if len(sys.argv) > 2 else 60
nombre_salida_emg = f"{prefijo}_emg.parquet"
nombre_salida_imu = f"{prefijo}_imu.parquet"
nombre_salida_eventos = f"{prefijo}_eventos.parquet"

muestras_emg = []
muestras_imu = []
eventos = []
paquetes_emg_este_segundo = 0
paquetes_imu_este_segundo = 0
t_inicio = None

def cuando_llega_dato_emg(caracteristica, paquete):
    global paquetes_emg_este_segundo
    muestras_emg.extend(desempaquetar_emg(paquete))
    paquetes_emg_este_segundo += 1

def cuando_llega_dato_imu(caracteristica, paquete):
    global paquetes_imu_este_segundo
    x, y, z = struct.unpack("<3f", paquete)
    t = time.perf_counter() - t_inicio
    muestras_imu.append((t, x, y, z))
    paquetes_imu_este_segundo += 1

def cuando_llega_evento(caracteristica, paquete):
    evento = desempaquetar_evento(paquete)
    t = time.perf_counter() - t_inicio
    nombre = NOMBRE_EVENTO.get(evento["tipo"], f"DESCONOCIDO({evento['tipo']})")
    eventos.append((t, nombre, evento["muestra"]))
    print(f"\n>>> [EVENTO] {nombre} en muestra EMG #{evento['muestra']} (t={t:.2f}s) <<<\n")

async def reportar_progreso(segundos):
    global paquetes_emg_este_segundo, paquetes_imu_este_segundo
    for _ in range(segundos):
        await asyncio.sleep(1)
        print(f"EMG: {paquetes_emg_este_segundo} paquetes/s ({len(muestras_emg)} acumuladas)  |  "
              f"IMU: {paquetes_imu_este_segundo} paquetes/s ({len(muestras_imu)} acumuladas)")
        paquetes_emg_este_segundo = 0
        paquetes_imu_este_segundo = 0

async def main():
    global t_inicio
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        t_inicio = time.perf_counter()
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato_emg)
        await client.start_notify(CARACTERISTICA_IMU, cuando_llega_dato_imu)
        await client.start_notify(CARACTERISTICA_EVENTOS, cuando_llega_evento)
        print(f"Escuchando {duracion_s}s (los datos EMG/IMU llegan automáticamente; START/STOP/MARK en la placa quedan registrados).")
        try:
            await reportar_progreso(duracion_s)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("Interrumpido por el usuario, guardando lo capturado hasta ahora...")

    columnas_emg = ["ch1", "ch2","ch3","ch4","ch5","ch6","ch7","ch8"]
    tabla_emg = pd.DataFrame(muestras_emg,columns=columnas_emg)
    tabla_emg.to_parquet(nombre_salida_emg)
    print(f"Guardadas {len(muestras_emg)} muestras EMG en {nombre_salida_emg}")

    tabla_imu = pd.DataFrame(muestras_imu, columns=["t", "x", "y", "z"])
    tabla_imu.to_parquet(nombre_salida_imu)
    print(f"Guardadas {len(muestras_imu)} muestras IMU en {nombre_salida_imu}")

    tabla_eventos = pd.DataFrame(eventos, columns=["t", "evento", "muestra_indice"])
    tabla_eventos.to_parquet(nombre_salida_eventos)
    print(f"Guardados {len(eventos)} eventos en {nombre_salida_eventos}")

try:
    asyncio.run(main())
except KeyboardInterrupt:
    # Red de seguridad por si Ctrl+C llega fuera del try interior.
    pass

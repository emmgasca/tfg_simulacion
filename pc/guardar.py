import asyncio
import struct
import sys
import time
import pandas as pd
from bleak import BleakClient
from protocolo_emg import desempaquetar_emg

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
CARACTERISTICA_IMU = "CCCCCCCC-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

# Nombre de fichero opcional: python guardar.py con_lamina
# -> guarda en con_lamina_emg.parquet / con_lamina_imu.parquet
# Sin argumento, usa los nombres de siempre (captura_emg.parquet / captura_imu.parquet).
prefijo = sys.argv[1] if len(sys.argv) > 1 else "captura"
nombre_salida_emg = f"{prefijo}_emg.parquet"
nombre_salida_imu = f"{prefijo}_imu.parquet"

muestras_emg = []
muestras_imu = []
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
        print("Escuchando 60s (los datos EMG/IMU llegan automáticamente; START/STOP en la placa es opcional para pausar).")
        await reportar_progreso(60)

    columnas_emg = ["ch1", "ch2","ch3","ch4","ch5","ch6","ch7","ch8"]
    tabla_emg = pd.DataFrame(muestras_emg,columns=columnas_emg)
    tabla_emg.to_parquet(nombre_salida_emg)
    print(f"Guardadas {len(muestras_emg)} muestras EMG en {nombre_salida_emg}")

    tabla_imu = pd.DataFrame(muestras_imu, columns=["t", "x", "y", "z"])
    tabla_imu.to_parquet(nombre_salida_imu)
    print(f"Guardadas {len(muestras_imu)} muestras IMU en {nombre_salida_imu}")

asyncio.run(main())

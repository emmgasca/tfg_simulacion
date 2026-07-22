import asyncio
import struct
import time
import pandas as pd
from bleak import BleakClient
from protocolo_emg import desempaquetar_emg

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
CARACTERISTICA_IMU = "CCCCCCCC-1234-1234-1234-123456789ABC"
CARACTERISTICA_EVENTOS = "EEEEEEEE-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

NOMBRE_EVENTO = {0: "STOP", 1: "START", 2: "MARK"}

muestras_emg = []
muestras_imu = []
eventos = []
t_inicio = None


def cuando_llega_dato_emg(caracteristica, paquete):
    muestras_emg.extend(desempaquetar_emg(paquete))


def cuando_llega_dato_imu(caracteristica, paquete):
    x, y, z = struct.unpack("<3f", paquete)
    t = time.perf_counter() - t_inicio
    muestras_imu.append((t, x, y, z))


def cuando_llega_evento(caracteristica, paquete):
    tipo, muestra_indice = struct.unpack("<BI", paquete)
    t = time.perf_counter() - t_inicio
    nombre = NOMBRE_EVENTO.get(tipo, f"DESCONOCIDO({tipo})")
    eventos.append((t, nombre, muestra_indice))
    print(f"Evento: {nombre} en muestra EMG #{muestra_indice} (t={t:.3f}s)")


async def main():
    global t_inicio
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        t_inicio = time.perf_counter()
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato_emg)
        await client.start_notify(CARACTERISTICA_IMU, cuando_llega_dato_imu)
        await client.start_notify(CARACTERISTICA_EVENTOS, cuando_llega_evento)
        await asyncio.sleep(60)

    columnas_emg = ["ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8"]
    tabla_emg = pd.DataFrame(muestras_emg, columns=columnas_emg)
    tabla_emg.to_parquet("captura_emg.parquet")
    print(f"Guardadas {len(muestras_emg)} muestras EMG en captura_emg.parquet")

    tabla_imu = pd.DataFrame(muestras_imu, columns=["t", "x", "y", "z"])
    tabla_imu.to_parquet("captura_imu.parquet")
    print(f"Guardadas {len(muestras_imu)} muestras IMU en captura_imu.parquet")

    tabla_eventos = pd.DataFrame(eventos, columns=["t", "evento", "muestra_indice"])
    tabla_eventos.to_parquet("captura_eventos.parquet")
    print(f"Guardados {len(eventos)} eventos en captura_eventos.parquet")

asyncio.run(main())

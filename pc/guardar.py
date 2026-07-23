import asyncio
import pandas as pd
from bleak import BleakClient
from protocolo_emg import desempaquetar_emg

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

muestras_emg = []
paquetes_este_segundo = 0

def cuando_llega_dato_emg(caracteristica, paquete):
    global paquetes_este_segundo
    muestras_emg.extend(desempaquetar_emg(paquete))
    paquetes_este_segundo += 1

async def reportar_progreso(segundos):
    global paquetes_este_segundo
    for _ in range(segundos):
        await asyncio.sleep(1)
        print(f"[EMG] recibidos {paquetes_este_segundo} paquetes en el último segundo "
              f"({len(muestras_emg)} muestras acumuladas)")
        paquetes_este_segundo = 0

async def main():
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato_emg)
        print("Escuchando 60s (los datos EMG llegan automáticamente; START/STOP en la placa es opcional para pausar).")
        await reportar_progreso(60)

    columnas_emg = ["ch1", "ch2","ch3","ch4","ch5","ch6","ch7","ch8"]
    tabla_emg = pd.DataFrame(muestras_emg,columns=columnas_emg)
    tabla_emg.to_parquet("captura_emg.parquet")
    print(f"Guardadas {len(muestras_emg)} muestras en captura_emg.parquet")

asyncio.run(main())

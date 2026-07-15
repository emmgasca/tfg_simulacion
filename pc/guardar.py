import asyncio
import struct
import pandas as pd
from bleak import BleakClient

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
DIRECCION = "E8:3D:C1:F6:09:09"
valores = []

def cuando_llega_dato(caracteristica, datos):
    valor = struct.unpack('<f', datos)[0]
    valores.append(valor)

async def main():
    async with BleakClient(DIRECCION) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato)
        await asyncio.sleep(5)
    # estas lineas van DENTRO de main pero FUERA del async with
    # (mismo nivel que el async with), para guardar una sola vez al terminar:
    df = pd.DataFrame({"emg": valores})
    df.to_parquet("captura_emg.parquet")
    print(f"Guardadas {len(valores)} muestras en captura_emg.parquet")

asyncio.run(main())

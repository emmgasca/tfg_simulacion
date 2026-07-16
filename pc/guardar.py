import asyncio
import struct
import pandas as pd
from bleak import BleakClient

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"
muestras_emg = []

def cuando_llega_dato(caracteristica, paquete):
    valor = struct.unpack('<f', paquete)[0]
    muestras_emg.append(valor)

async def main():
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato)
        await asyncio.sleep(5)
    
    tabla_emg = pd.DataFrame({"emg": muestras_emg})
    tabla_emg.to_parquet("captura_emg.parquet")
    print(f"Guardadas {len(muestras_emg)} muestras en captura_emg.parquet")

asyncio.run(main())

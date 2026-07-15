import asyncio
from bleak import BleakClient
import struct

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
DIRECCION = "E8:3D:C1:F6:09:09"

def cuando_llega_dato(caracteristica, datos):
    valor = struct.unpack('<f', datos)[0]
    print(valor)
    
async def main():
    async with BleakClient(DIRECCION) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato)
        await asyncio.sleep(5)

asyncio.run(main())


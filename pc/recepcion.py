
import asyncio
from bleak import BleakClient
import struct

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

def cuando_llega_dato(caracteristica, paquete):
    valor = struct.unpack('<f', paquete)[0]
    print(valor)

async def main():
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato)
        await asyncio.sleep(5)

asyncio.run(main())

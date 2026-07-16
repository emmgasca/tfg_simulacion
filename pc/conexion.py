import asyncio
from bleak import BleakClient

DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

async def main():
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")

asyncio.run(main())
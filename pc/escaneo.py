import asyncio
from bleak import BleakScanner

async def main():
    dispositivos_encontrados = await BleakScanner.discover()
    for dispositivo in dispositivos_encontrados:
        print(dispositivo.name, dispositivo.address)

asyncio.run(main())

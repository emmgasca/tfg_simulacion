### Paso 1 - Escanear y ver la placa  

import asyncio
from bleak import BleakScanner

async def main():
    dispositivos_encontrados = await BleakScanner.discover()
    for dispositivo in dispositivos_encontrados:
        print(dispositivo.name, dispositivo.address)

asyncio.run(main())

### Paso 2 - Conectarse a la placa 

import asyncio
from bleak import BleakClient

DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

async def main():
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")

asyncio.run(main())

### Paso 3 - Recibir la señal e imprimir números decodificados

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

### Paso 4 - Guardar en Parquet

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

### Paso 6 - Abrir paquete y dibujar señal en una gráfica

import pandas as pd
import matplotlib.pyplot as plt

tabla_emg = pd.read_parquet("captura_emg.parquet")
print(tabla_emg)

plt.plot(tabla_emg["emg"])
plt.xlabel("muestra")
plt.ylabel("valor EMG")
plt.title("Señal capturada")
plt.show()
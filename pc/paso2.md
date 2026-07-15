## Paso 2 — Conectarse a la placa  ✅

Objetivo: abrir la conexión con la placa (equivale a darle "Connect" en nRF Connect
y ver "Connected"). No se leen datos todavía.

Cambios respecto al Paso 1:
- Se usa `BleakClient` (conectar a uno concreto) en vez de `BleakScanner` (buscar).
- Se conecta por MAC (`E8:3D:C1:F6:09:09`) para no depender del nombre genérico "ESP32".
- El bloque `async with BleakClient(...) as client:` abre la conexión y la cierra
  sola al salir, aunque haya un error.

`pc/conexion.py`:
```python
import asyncio
from bleak import BleakClient

DIRECCION = "E8:3D:C1:F6:09:09"

async def main():
    async with BleakClient(DIRECCION) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")

asyncio.run(main())
```

Resultado: `Conectado al dispositivo BLE: True`  -> el PC se conecta a la placa. (OK)

Notas:
- `client.is_connected` devuelve True/False segun el estado de la conexion.
- La conexion tarda un par de segundos; al salir del bloque desconecta sola.
- Recordatorio: desconectar la ESP32 en nRF Connect del movil antes de probar
  (solo admite una conexion a la vez).
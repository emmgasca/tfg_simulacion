# Recepción BLE en el PC — Cuaderno de bitácora

Proyecto: recibir en el PC los datos EMG que la ESP32 emite por BLE, guardarlos
en `.parquet` y analizar si hay ruido. Herramienta: **bleak** (librería Python de BLE).

---

## Datos de la placa (confirmados)

- **Nombre BLE:** `ESP32`
- **Dirección MAC:** `E8:3D:C1:F6:09:09`

### Servicio EMG (`12345678-1234-1234-1234-123456789ABC`)
- `AAAAAAAA-1234-1234-1234-123456789ABC` → **Notify** (datos EMG) ← me suscribo a esta
- `BBBBBBBB-...` → Write (config, no la necesito ahora)

### Servicio IMU (`87654321-1234-1234-1234-123456789ABC`)
- `CCCCCCCC-...` → Notify (datos IMU)
- `DDDDDDDD-...` → Write (config)

**Arranque:** el firmware empieza a notificar solo al conectarse (sin paso de config previo).

---

## Entorno de trabajo

- Python de trabajo: el de la cajita `.venv` (entorno virtual creado con `uv`).
- bleak instalado dentro de esa cajita.
- La cajita se reconoce por `(TFG_simulacion)` al principio de la línea de terminal.

### Lección clave
Tengo varios Python instalados. **bleak tiene que estar en el mismo Python que ejecuta
el programa.** Todo el enredo inicial fue por instalar bleak en un Python y ejecutar con otro.
La cajita `.venv` resuelve esto aislando las librerías del proyecto.

---

## Comandos de terminal (en orden, solo los que funcionaron)

```powershell
# 1. Crear la cajita (entorno virtual). Solo una vez.
uv venv

# 2. Activar la cajita (VSCode lo hizo con este comando).
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& c:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\.venv\Scripts\Activate.ps1)
# -> tras esto la linea empieza por (TFG_simulacion) = cajita activa

# 3. Instalar bleak dentro de la cajita. Solo una vez.
uv pip install bleak

# 4. Ejecutar el escaneo.
python pc\escaneo.py
# -> salio: ESP32 E8:3D:C1:F6:09:09  (OK)
```

### Para retomar el trabajo (tras cerrar VSCode)
La cajita y bleak ya están instalados. Solo hay que **activar** la cajita otra vez (paso 2).
No repito el 1 ni el 3.

Alternativa sin activar (llamar directo al Python de la cajita):
```powershell
.venv\Scripts\python.exe pc\escaneo.py
```

---

## Pasos

### Paso 0 — Probar que Python funciona  ✅
Archivo con `print("hola")` -> salió `hola`.

### Paso 1 — Escanear y ver la placa  ✅
`pc/escaneo.py`:
```python
import asyncio
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover()
    for device in devices:
        print(device.name, device.address)

asyncio.run(main())
```
Resultado: apareció `ESP32 E8:3D:C1:F6:09:09`. Tubería BLE confirmada.

### Paso 2 — Conectarse a la placa  (pendiente)
Usar `BleakClient` en vez de `BleakScanner`. Abrir y cerrar conexión, sin leer datos aún.
Conectar por MAC (`E8:3D:C1:F6:09:09`) para no depender del nombre genérico "ESP32".

### Paso 3 — Suscribirse a `AAAAAAAA` y ver paquetes crudos  (pendiente)
Confirmar tamaño de paquete y que el contador incremente sin huecos.

### Paso 4 — Decodificar  (pendiente)
int24 con signo del ADS1298. Opcional: escalar a µV con `Vref / (gain * (2^23 - 1))`.

### Paso 5 — Guardar en `.parquet`  (pendiente)
Por bloques (row groups), nunca muestra a muestra (Parquet fila a fila es lentísimo).

### Paso 6 — Analizar ruido  (pendiente)
Desviación estándar + FFT. Pico en 50 Hz = red eléctrica.

---

## Recordatorio recurrente
Antes de cada prueba de conexión desde el PC: **desconectar la ESP32 en nRF Connect
del móvil** (Disconnect). Muchos periféricos BLE aceptan una sola conexión a la vez.
Comandos de terminal ejecutados (en orden)

Para crear
New-Item pc\notas.md
Para abrir
code pc\notas.md
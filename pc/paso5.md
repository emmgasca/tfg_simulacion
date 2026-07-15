## Paso 4 — Decodificar el float  ✅

Objetivo: convertir los 4 bytes crudos de cada notificacion en el numero real (float),
para ver el seno como valores legibles en vez de hexadecimal.

Piezas nuevas:
- `import struct`: modulo estandar de Python (viene incluido) para convertir bytes <-> numeros.
- `struct.unpack('<f', datos)[0]`:
  - `<` = little-endian (el orden que usa el ESP32, confirmado en el firmware).
  - `f` = float de 4 bytes.
  - `[0]` = unpack devuelve una lista; se coge el primer (y unico) elemento.

Cambio en el callback:
```python
def cuando_llega_dato(caracteristica, datos):
    valor = struct.unpack('<f', datos)[0]
    print(valor)
```

Resultado: numeros decimales subiendo y bajando suave entre -1.0 y +1.0 (el seno).
Picos en +0.9999 y -0.9999 -> decodificacion correcta.
Ademas confirma que el **little-endian era correcto** (si estuviera mal, saldrian
numeros disparatados en vez de un seno limpio).

---

## Paso 5 — Guardar en Parquet  (en curso)

Objetivo: acumular los valores decodificados y guardarlos en un archivo `.parquet`.

Regla clave: **NO escribir muestra a muestra** (seria lentisimo). El patron correcto:
1. Cada valor que llega -> se anade a una **lista** en memoria (rapido).
2. Al terminar la captura -> se vuelca la lista entera a Parquet de una vez.

Librerias nuevas (instalar una vez, con la cajita activa):
```
uv pip install pandas pyarrow
```
- `pandas`: maneja tablas de datos en Python (estandar).
- `pyarrow`: motor que escribe el formato Parquet.

### Donde va la lista de valores
La lista `valores = []` va **arriba, con las demas variables, FUERA de las funciones**.
Motivo: tiene que ser visible por todas las funciones. El callback le anade valores
(`.append`) y `main` la lee al final para guardarla. Si estuviera dentro de una funcion,
solo existiria ahi y la otra no la veria.
Como el callback solo hace `.append()` (modifica, no reasigna), funciona directamente.

### Codigo completo (`pc/guardar.py`)
```python
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
```

Cuidado con la indentacion: las lineas de guardar (`df = ...`, `to_parquet`, `print`)
van dentro de `main` pero fuera del `async with`. Si las metes dentro del `with`,
guardaria en cada paquete (mal).

Resultado esperado: un archivo `captura_emg.parquet` en la carpeta, y un mensaje
tipo "Guardadas 1000 muestras en captura_emg.parquet".
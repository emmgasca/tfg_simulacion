import asyncio
import time
from bleak import BleakClient
from protocolo_emg import desempaquetar_emg
from protocolo_eventos import desempaquetar_evento

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
CARACTERISTICA_EVENTOS = "EEEEEEEE-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

contador_paquetes_emg = 0
ultimo_reporte = time.time()

def cuando_llega_emg(caracteristica, paquete):
    global contador_paquetes_emg, ultimo_reporte
    contador_paquetes_emg += 1
    ahora = time.time()
    if ahora - ultimo_reporte >= 1.0:
        print(f"[EMG] recibidos {contador_paquetes_emg} paquetes en el último segundo")
        contador_paquetes_emg = 0
        ultimo_reporte = ahora

def cuando_llega_evento(caracteristica, paquete):
    evento = desempaquetar_evento(paquete)
    tipos = {0: "START", 1: "STOP", 2: "MARK"}
    nombre = tipos.get(evento['tipo'], '?')
    print(f"\n>>> [EVENTO] {nombre} en muestra {evento['muestra']} (t={evento['timestamp_ms']}ms) <<<\n")
    if nombre == "START":
        print("### Sesión activa: ya puedes pulsar MARK ###")
    elif nombre == "STOP":
        print("### Sesión cerrada ###")
        
async def main():
    async with BleakClient(DIRECCION_PLACA) as client:
        print(f"Conectado: {client.is_connected}")
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_emg)
        await client.start_notify(CARACTERISTICA_EVENTOS, cuando_llega_evento)
        print("Escuchando 60s. Pulsa START, espera, MARK, espera, STOP en la placa...")
        await asyncio.sleep(60)

asyncio.run(main())
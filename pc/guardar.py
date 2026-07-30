import asyncio
import struct
import sys
import time
import pandas as pd
from bleak import BleakClient, BleakScanner
from protocolo_emg import desempaquetar_emg, leer_secuencia, PaqueteEMGInvalido
from protocolo_eventos import desempaquetar_evento

CARACTERISTICA_EMG = "AAAAAAAA-1234-1234-1234-123456789ABC"
CARACTERISTICA_IMU = "CCCCCCCC-1234-1234-1234-123456789ABC"
CARACTERISTICA_EVENTOS = "EEEEEEEE-1234-1234-1234-123456789ABC"
DIRECCION_PLACA = "E8:3D:C1:F6:09:09"

NOMBRE_EVENTO = {0: "START", 1: "STOP", 2: "MARK"}

# Uso: python guardar.py [nombre] [duracion_s]
# -> guarda en <nombre>_emg.parquet / <nombre>_imu.parquet / <nombre>_eventos.parquet,
#    escuchando duracion_s segundos.
# Sin argumentos: nombre "captura", duracion 60s (como antes).
prefijo = sys.argv[1] if len(sys.argv) > 1 else "captura"
duracion_s = int(sys.argv[2]) if len(sys.argv) > 2 else 60
nombre_salida_emg = f"{prefijo}_emg.parquet"
nombre_salida_imu = f"{prefijo}_imu.parquet"
nombre_salida_eventos = f"{prefijo}_eventos.parquet"

MUESTRAS_POR_PAQUETE_EMG = 8  # debe coincidir con MUESTRAS_POR_PAQUETE en BLE.cpp

muestras_emg = []
muestras_imu = []
eventos = []
paquetes_emg_este_segundo = 0
paquetes_imu_este_segundo = 0
paquetes_emg_totales = 0
paquetes_emg_perdidos = 0  # en MUESTRAS, no en paquetes: la secuencia ahora es por muestra
paquetes_emg_corruptos = 0
siguiente_secuencia_esperada = None
muestras_firmware_en_stop = None
t_inicio = None

def cuando_llega_dato_emg(caracteristica, paquete):
    global paquetes_emg_este_segundo, paquetes_emg_totales, paquetes_emg_corruptos
    global siguiente_secuencia_esperada, paquetes_emg_perdidos

    try:
        secuencia_base = leer_secuencia(paquete)
        canales_por_muestra = desempaquetar_emg(paquete)
    except PaqueteEMGInvalido as error:
        # Paquete que SI llego por el aire pero esta corrupto o mal formado
        # (CRC invalido, magic/version/tamano incorrectos) -- distinto de un
        # paquete perdido, que ni siquiera llega.
        paquetes_emg_corruptos += 1
        print(f"AVISO: paquete EMG corrupto descartado -- {error}")
        return

    if siguiente_secuencia_esperada is not None and secuencia_base != siguiente_secuencia_esperada:
        salto = (secuencia_base - siguiente_secuencia_esperada) & 0xFFFFFFFF
        paquetes_emg_perdidos += salto
        # Sin print() aqui a proposito: con ~35% de perdida, esto puede saltar
        # decenas de veces por segundo, y cada print() es E/S de consola que
        # puede bloquear el bucle de asyncio el tiempo suficiente para perder
        # AUN MAS notificaciones BLE mientras Python esta ocupado escribiendo
        # en pantalla. El resumen final ya reporta el total.
    siguiente_secuencia_esperada = (secuencia_base + len(canales_por_muestra)) & 0xFFFFFFFF

    # Se guarda la secuencia real de CADA muestra (no la del paquete repetida)
    # para poder analizar despues, directamente sobre el parquet, cada cuanto
    # y donde se pierden muestras (con un diff() sobre esta columna), sin
    # depender de mirar la consola en directo.
    for i, canales in enumerate(canales_por_muestra):
        muestras_emg.append((secuencia_base + i,) + canales)
    paquetes_emg_este_segundo += 1
    paquetes_emg_totales += 1

def cuando_llega_dato_imu(caracteristica, paquete):
    global paquetes_imu_este_segundo
    x, y, z = struct.unpack("<3f", paquete)
    t = time.perf_counter() - t_inicio
    muestras_imu.append((t, x, y, z))
    paquetes_imu_este_segundo += 1

def cuando_llega_evento(caracteristica, paquete):
    global muestras_firmware_en_stop
    evento = desempaquetar_evento(paquete)
    t = time.perf_counter() - t_inicio
    nombre = NOMBRE_EVENTO.get(evento["tipo"], f"DESCONOCIDO({evento['tipo']})")
    eventos.append((t, nombre, evento["muestra"]))
    print(f"\n>>> [EVENTO] {nombre} en muestra EMG #{evento['muestra']} (t={t:.2f}s) <<<\n")
    if nombre == "STOP":
        # contadorMuestras del firmware: cuantas muestras EMG proceso desde el
        # ultimo START, independientemente de si ya se enviaron por BLE o no.
        muestras_firmware_en_stop = evento["muestra"]

async def reportar_progreso(segundos):
    global paquetes_emg_este_segundo, paquetes_imu_este_segundo
    for _ in range(segundos):
        await asyncio.sleep(1)
        print(f"EMG: {paquetes_emg_este_segundo} paquetes/s ({len(muestras_emg)} acumuladas)  |  "
              f"IMU: {paquetes_imu_este_segundo} paquetes/s ({len(muestras_imu)} acumuladas)")
        paquetes_emg_este_segundo = 0
        paquetes_imu_este_segundo = 0

async def main():
    global t_inicio
    # En Windows (backend WinRT de Bleak), conectar directo por MAC sin haber
    # escaneado antes suele fallar con "Device was not found" si el SO no
    # tiene el anuncio BLE en su cache reciente. Se busca primero el
    # dispositivo explicitamente (con reintentos) y se conecta a ese objeto.
    dispositivo = None
    for intento in range(3):
        print(f"Buscando la placa ({DIRECCION_PLACA})... intento {intento + 1}/3")
        dispositivo = await BleakScanner.find_device_by_address(DIRECCION_PLACA, timeout=10)
        if dispositivo is not None:
            break
    if dispositivo is None:
        print("No se encontro la placa. Comprueba que este encendida, "
              "anunciandose por BLE (LED azul) y sin otra app ya conectada a ella.")
        return

    async with BleakClient(dispositivo) as client:
        print(f"Conectado al dispositivo BLE: {client.is_connected}")
        t_inicio = time.perf_counter()
        await client.start_notify(CARACTERISTICA_EMG, cuando_llega_dato_emg)
        await client.start_notify(CARACTERISTICA_IMU, cuando_llega_dato_imu)
        await client.start_notify(CARACTERISTICA_EVENTOS, cuando_llega_evento)
        print(f"Escuchando {duracion_s}s (los datos EMG/IMU llegan automáticamente; START/STOP/MARK en la placa quedan registrados).")
        try:
            await reportar_progreso(duracion_s)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("Interrumpido por el usuario, guardando lo capturado hasta ahora...")

    columnas_emg = ["paquete_id", "ch1", "ch2","ch3","ch4","ch5","ch6","ch7","ch8"]
    tabla_emg = pd.DataFrame(muestras_emg,columns=columnas_emg)
    tabla_emg.to_parquet(nombre_salida_emg)
    print(f"Guardadas {len(muestras_emg)} muestras EMG en {nombre_salida_emg}")

    tabla_imu = pd.DataFrame(muestras_imu, columns=["t", "x", "y", "z"])
    tabla_imu.to_parquet(nombre_salida_imu)
    print(f"Guardadas {len(muestras_imu)} muestras IMU en {nombre_salida_imu}")

    tabla_eventos = pd.DataFrame(eventos, columns=["t", "evento", "muestra_indice"])
    tabla_eventos.to_parquet(nombre_salida_eventos)
    print(f"Guardados {len(eventos)} eventos en {nombre_salida_eventos}")

    print(f"\nPaquetes EMG recibidos por BLE: {paquetes_emg_totales}")
    print(f"Paquetes EMG corruptos descartados (CRC/formato invalido): {paquetes_emg_corruptos}")
    print(f"Muestras EMG decodificadas: {len(muestras_emg)}")

    # Deteccion por numero de secuencia (ahora por MUESTRA, no por paquete):
    # funciona siempre, sin depender de haber pulsado START/STOP
    # (grabando=true desde el arranque).
    if paquetes_emg_perdidos == 0:
        print("OK: ninguna muestra EMG perdida por el aire (secuencia sin huecos). "
              "Esto NO detecta muestras descartadas en el ESP32 antes de formar el "
              "paquete (p. ej. cola llena porque BLE no drena tan rapido como el ADC); "
              "para eso, mira la comparacion con el contador del firmware tras STOP.")
    else:
        print(f"AVISO: se detectaron ~{paquetes_emg_perdidos} muestras EMG perdidas por el aire.")


    if muestras_firmware_en_stop is not None:
        paquetes_esperados = muestras_firmware_en_stop // MUESTRAS_POR_PAQUETE_EMG
        perdidas = muestras_firmware_en_stop - len(muestras_emg)
        print(f"Muestras procesadas por el firmware (segun evento STOP): {muestras_firmware_en_stop}")
        print(f"Paquetes BLE esperados (muestras_firmware // {MUESTRAS_POR_PAQUETE_EMG}): {paquetes_esperados}")
        if perdidas <= MUESTRAS_POR_PAQUETE_EMG - 1:
            print(f"OK: diferencia de {perdidas} muestras, dentro del margen normal "
                  f"(el ultimo paquete parcial, <{MUESTRAS_POR_PAQUETE_EMG} muestras, no se envia hasta llenarse).")
        else:
            print(f"AVISO: faltan {perdidas} muestras respecto a lo que proceso el firmware "
                  f"-- posible perdida de paquetes BLE (notify sin ACK).")
    else:
       print("No se recibio evento STOP: no se puede comparar con el contador del firmware.")

try:
    asyncio.run(main())
except KeyboardInterrupt:
   
    pass

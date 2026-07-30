"""Desempaquetado del protocolo EMG enviado por BLE.

Este archivo es el espejo, en Python, de como el ESP32 arma el paquete en
BLE.cpp: si algo cambia alli, tiene que cambiar aqui tambien.

Cada paquete que llega por Bluetooth trae varias muestras EMG agrupadas,
con esta forma (basada en el proyecto ParkEMG, streamlit_emg_live.py):

    ["PB"] [version] [num_muestras] [num_secuencia] [tam_muestra] [datos EMG...] [CRC16]

- "num_secuencia" es el numero de la PRIMERA muestra de este paquete
  (no del paquete en si). Como cada paquete trae varias muestras
  seguidas, sabiendo la primera se puede calcular la secuencia de todas:
  muestra i del paquete -> secuencia = num_secuencia + i. Esto permite
  detectar exactamente cuantas muestras faltan si se pierde un paquete,
  sin depender de los botones START/STOP/MARK.
- "CRC16" es un codigo de verificacion (ver crc16_ccitt() mas abajo):
  detecta si el paquete ha llegado con algun dato corrompido por el
  camino (interferencia de radio), aunque tenga el tamaño correcto.

Nota importante: una prueba A/B (con y sin CRC/magic/version, mismo
tamaño de paquete) confirmo que el CRC NO era lo que arreglaba la perdida
de paquetes -- eso lo arreglo el tamaño de paquete (MUESTRAS_POR_PAQUETE=8)
y el ajuste de la conexion BLE, ambos en BLE.cpp. El CRC se mantiene aun
asi porque protege la integridad de la señal fisiologica, no porque
mejore el rendimiento.
"""

NUM_CANALES = 8
BYTES_POR_CANAL = 3
BYTES_POR_MUESTRA = NUM_CANALES * BYTES_POR_CANAL  # 24

LOTE_MAGIC = b"PB"
LOTE_VERSION = 2
LOTE_CABECERA = 9  # magic(2) + version(1) + num_muestras(1) + secuencia(4) + frame_size(1)
LOTE_CRC = 2


class PaqueteEMGInvalido(ValueError):
    """El paquete no tiene el formato esperado, o falla la verificacion de CRC."""


def crc16_ccitt(datos):
    """Calcula el mismo "codigo de verificacion" de 16 bits que calculo el
    ESP32 antes de enviar. Si no coincide con el CRC que viene en el
    paquete, algun byte ha cambiado por el camino (interferencia de
    radio) y el paquete se descarta como corrupto.
    Algoritmo CRC16-CCITT (poli 0x1021, init 0xFFFF, MSB primero) -- igual
    que en streamlit_emg_live.py y en BLE.cpp, para que las tres partes
    calculen siempre el mismo valor."""
    crc = 0xFFFF
    for byte in datos:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def decodificar_int24(b0, b1, b2):
    valor = (b0 << 16) | (b1 << 8) | b2
    if valor & 0x800000:
        valor -= 0x1000000
    return valor


def _validar_paquete(paquete):
    """Comprueba magic/version/tamano/CRC. Lanza PaqueteEMGInvalido si algo falla."""
    if len(paquete) < LOTE_CABECERA + LOTE_CRC:
        raise PaqueteEMGInvalido(f"paquete demasiado corto: {len(paquete)} bytes")
    if paquete[0:2] != LOTE_MAGIC:
        raise PaqueteEMGInvalido(f"magic incorrecto: {paquete[0:2]!r}")
    if paquete[2] != LOTE_VERSION:
        raise PaqueteEMGInvalido(f"version no soportada: {paquete[2]}")

    num_muestras = paquete[3]
    frame_size = paquete[8]
    payload_len = num_muestras * frame_size
    tamano_esperado = LOTE_CABECERA + payload_len + LOTE_CRC
    if len(paquete) != tamano_esperado:
        raise PaqueteEMGInvalido(
            f"tamano de paquete inesperado: {len(paquete)} (se esperaba {tamano_esperado})"
        )

    crc_offset = LOTE_CABECERA + payload_len
    crc_recibido = int.from_bytes(paquete[crc_offset:crc_offset + LOTE_CRC], byteorder="little")
    crc_calculado = crc16_ccitt(paquete[:crc_offset])
    if crc_recibido != crc_calculado:
        raise PaqueteEMGInvalido(
            f"CRC invalido: recibido=0x{crc_recibido:04X} calculado=0x{crc_calculado:04X}"
        )


def leer_secuencia(paquete):
    """Numero de secuencia de la PRIMERA muestra del lote (32 bits, con vuelta a 0)."""
    _validar_paquete(paquete)
    return int.from_bytes(paquete[4:8], byteorder="little", signed=False)


def leer_num_muestras(paquete):
    """Cuantas muestras trae este lote (normalmente MUESTRAS_POR_PAQUETE de BLE.cpp)."""
    _validar_paquete(paquete)
    return paquete[3]


def desempaquetar_emg(paquete):
    """Convierte un paquete valido en una lista de muestras (una tupla de 8 canales cada una).

    Lanza PaqueteEMGInvalido si el magic/version/tamano/CRC no son correctos --
    quien llame debe capturarla para contar paquetes corruptos por separado de
    los perdidos por el aire.
    """
    _validar_paquete(paquete)
    num_muestras = paquete[3]
    frame_size = paquete[8]
    payload = paquete[LOTE_CABECERA:LOTE_CABECERA + num_muestras * frame_size]

    muestras = []
    for i in range(num_muestras):
        offset = i * frame_size
        canales = tuple(
            decodificar_int24(
                payload[offset + c * BYTES_POR_CANAL],
                payload[offset + c * BYTES_POR_CANAL + 1],
                payload[offset + c * BYTES_POR_CANAL + 2],
            )
            for c in range(NUM_CANALES)
        )
        muestras.append(canales)
    return muestras

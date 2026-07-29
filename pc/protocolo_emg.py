"""Desempaquetado del protocolo EMG enviado por BLE.

Formato de paquete adaptado del proyecto ParkEMG (streamlit_emg_live.py):
lote "PB" version 2 = magic(2) + version(1) + num_muestras(1) +
primera_secuencia(4, uint32 little-endian) + frame_size(1) +
payload(num_muestras * frame_size) + crc16(2, little-endian).

frame_size = 24 (8 canales x 3 bytes/canal): no incluye los 3 bytes de status
del ADS1298, igual que en la v2 de ParkEMG -- el firmware ya los descarta antes
de enviar.

La secuencia es POR MUESTRA (no por paquete): "primera_secuencia" identifica la
primera de las N muestras del lote, así que la muestra i del lote tiene
secuencia = primera_secuencia + i. Esto permite detectar huecos exactos en
numero de muestras perdidas, sin depender de eventos START/STOP/MARK.

El CRC16 (mismo algoritmo CCITT que usa ParkEMG: poli 0x1021, init 0xFFFF,
MSB primero) detecta paquetes que llegaron pero estan corruptos -- algo que un
simple numero de secuencia no puede ver.
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
    """CRC16-CCITT (poli 0x1021, init 0xFFFF, MSB primero) -- igual que en
    streamlit_emg_live.py, para que ambos lados calculen el mismo valor."""
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

"""Desempaquetado del protocolo EMG enviado por BLE.

Cada notify trae varias muestras agrupadas. Cada muestra son 8 canales,
codificados como entero de 24 bits con signo, big-endian (MSB primero),
tal como los entrega el ADS1298 por SPI (los 3 bytes de status del frame
ya se descartan en el firmware antes de enviarlos).
"""

NUM_CANALES = 8
BYTES_POR_CANAL = 3
BYTES_POR_MUESTRA = NUM_CANALES * BYTES_POR_CANAL  # 24


def decodificar_int24(b0, b1, b2):
    valor = (b0 << 16) | (b1 << 8) | b2
    if valor & 0x800000:
        valor -= 0x1000000
    return valor


def desempaquetar_emg(paquete):
    """Convierte el buffer crudo de un notify en una lista de muestras (una tupla de 8 canales cada una)."""
    num_muestras = len(paquete) // BYTES_POR_MUESTRA
    muestras = []
    for i in range(num_muestras):
        offset = i * BYTES_POR_MUESTRA
        canales = tuple(
            decodificar_int24(
                paquete[offset + c * BYTES_POR_CANAL],
                paquete[offset + c * BYTES_POR_CANAL + 1],
                paquete[offset + c * BYTES_POR_CANAL + 2],
            )
            for c in range(NUM_CANALES)
        )
        muestras.append(canales)
    return muestras

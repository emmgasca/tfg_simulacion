"""Desempaquetado del protocolo EMG enviado por BLE.

Cada notify trae una cabecera de 2 bytes (numero de secuencia, 16 bits,
little-endian) seguida de varias muestras agrupadas. Cada muestra son
8 canales, codificados como entero de 24 bits con signo (MSB primero),
tal como los entrega el ADS1298 por SPI (los 3 bytes de status del frame
ya se descartan en el firmware antes de enviarlos).

El numero de secuencia permite detectar paquetes perdidos por el aire
(notify no tiene ACK) sin depender de eventos START/STOP/MARK.
"""

NUM_CANALES = 8
BYTES_POR_CANAL = 3
BYTES_POR_MUESTRA = NUM_CANALES * BYTES_POR_CANAL  # 24
BYTES_CABECERA = 2


def decodificar_int24(b0, b1, b2):
    valor = (b0 << 16) | (b1 << 8) | b2
    if valor & 0x800000:
        valor -= 0x1000000
    return valor


def leer_secuencia(paquete):
    """Numero de secuencia (0-65535, con vuelta a 0) del paquete, puesto por el firmware."""
    return paquete[0] | (paquete[1] << 8)


def desempaquetar_emg(paquete):
    """Convierte el buffer crudo de un notify (sin la cabecera) en una lista
    de muestras (una tupla de 8 canales cada una)."""
    datos = paquete[BYTES_CABECERA:]
    num_muestras = len(datos) // BYTES_POR_MUESTRA
    muestras = []
    for i in range(num_muestras):
        offset = i * BYTES_POR_MUESTRA
        canales = tuple(
            decodificar_int24(
                datos[offset + c * BYTES_POR_CANAL],
                datos[offset + c * BYTES_POR_CANAL + 1],
                datos[offset + c * BYTES_POR_CANAL + 2],
            )
            for c in range(NUM_CANALES)
        )
        muestras.append(canales)
    return muestras

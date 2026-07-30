"""Desempaquetado del protocolo EMG enviado por BLE.

EXPERIMENTO: formato de antes de adaptarlo a ParkEMG. Paquete = contador de
PAQUETE (2 bytes, uint16 little-endian, con vuelta a 0) + N muestras de 24
bytes cada una (8 canales x 3 bytes/canal), N = MUESTRAS_POR_PAQUETE (fijo,
no viaja en el paquete -- a diferencia del formato PB v2, aqui no hay
magic/version/frame_size autodescriptivos). Sin CRC16: un paquete corrupto
pero del tamano correcto no se detecta como tal.

leer_secuencia() multiplica el contador de paquete por MUESTRAS_POR_PAQUETE
para devolver una secuencia POR MUESTRA, asi el resto del pipeline
(guardar.py, que espera esa semantica) no necesita ningun cambio.
"""

NUM_CANALES = 8
BYTES_POR_CANAL = 3
BYTES_POR_MUESTRA = NUM_CANALES * BYTES_POR_CANAL  # 24

MUESTRAS_POR_PAQUETE = 8  # debe coincidir con MUESTRAS_POR_PAQUETE en BLE.cpp
BYTES_CABECERA = 2  # contador de paquete, 16 bits, little-endian
BYTES_PAQUETE_EMG = MUESTRAS_POR_PAQUETE * BYTES_POR_MUESTRA
BYTES_NOTIFY_EMG = BYTES_CABECERA + BYTES_PAQUETE_EMG


class PaqueteEMGInvalido(ValueError):
    """El paquete no tiene el tamano esperado."""


def decodificar_int24(b0, b1, b2):
    valor = (b0 << 16) | (b1 << 8) | b2
    if valor & 0x800000:
        valor -= 0x1000000
    return valor


def _validar_paquete(paquete):
    if len(paquete) != BYTES_NOTIFY_EMG:
        raise PaqueteEMGInvalido(
            f"tamano de paquete inesperado: {len(paquete)} (se esperaba {BYTES_NOTIFY_EMG})"
        )


def leer_secuencia(paquete):
    """Secuencia de la PRIMERA muestra del lote, reconstruida a partir del
    contador de paquete (unico dato que viaja en este formato antiguo)."""
    _validar_paquete(paquete)
    contador_paquete = int.from_bytes(paquete[0:BYTES_CABECERA], byteorder="little", signed=False)
    return (contador_paquete * MUESTRAS_POR_PAQUETE) & 0xFFFFFFFF


def leer_num_muestras(paquete):
    _validar_paquete(paquete)
    return MUESTRAS_POR_PAQUETE


def desempaquetar_emg(paquete):
    """Convierte un paquete valido en una lista de muestras (una tupla de 8 canales cada una).

    Lanza PaqueteEMGInvalido si el tamano no es el esperado -- quien llame
    debe capturarla para contar paquetes corruptos por separado de los
    perdidos por el aire.
    """
    _validar_paquete(paquete)
    payload = paquete[BYTES_CABECERA:]

    muestras = []
    for i in range(MUESTRAS_POR_PAQUETE):
        offset = i * BYTES_POR_MUESTRA
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

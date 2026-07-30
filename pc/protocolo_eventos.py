"""Desempaqueta los eventos START/STOP/MARK que manda el ESP32 al pulsar
un boton fisico. Formato fijo de 9 bytes: tipo de evento (1 byte) +
numero de muestra EMG en ese instante (4 bytes) + timestamp en ms
(4 bytes). Tiene que coincidir con la struct EventoBLE de botones.h."""

import struct

def desempaquetar_evento(paquete):
    tipo, muestra, timestamp_ms = struct.unpack('<BII', paquete)
    return {"tipo": tipo, "muestra": muestra, "timestamp_ms": timestamp_ms}
import struct

def desempaquetar_evento(paquete):
    tipo, muestra, timestamp_ms = struct.unpack('<BII', paquete)
    return {"tipo": tipo, "muestra": muestra, "timestamp_ms": timestamp_ms}
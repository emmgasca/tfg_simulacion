# Vista alternativa a analizar.py, pensada para el ensayo de cortocircuito:
# dibuja los 8 canales superpuestos en una sola grafica (un solo eje X y
# un solo eje Y), cada uno desplazado verticalmente, todos en microvoltios.
#
# El desplazamiento se calcula automaticamente a partir del rango real de
# los datos (no es un numero fijo), para que se vean bien separados tanto
# si estan saturados (valores grandes) como si ya estan limpios (valores
# pequeños en uV).
#
# Util para localizar en que segundo cambia un canal concreto, por
# ejemplo en el ensayo de cortocircuito, tocando uno a uno los
# electrodos de la matriz durante una misma grabacion continua.
#
# Uso: python analizar_cortocircuito.py [nombre_emg.parquet]
# Sin argumentos, usa captura_emg.parquet. El HTML se guarda con el
# mismo prefijo que el parquet de entrada (p. ej. cortocircuito_emg.parquet
# -> cortocircuito_analisis_cortocircuito.html).
import sys

import pandas as pd
import numpy as np
import plotly.graph_objects as go

VREF = 2.4      # V, confirmado con CONFIG3 (VREF_4V=0) en ads1298.cpp
GANANCIA = 6    # confirmado con CHnSET (GAINn=000) en ads1298.cpp
LSB_UV = (2 * VREF) / (GANANCIA * 2**24) * 1e6  # microvoltios por cuenta ADC

ruta_emg = sys.argv[1] if len(sys.argv) > 1 else "captura_emg.parquet"
prefijo = ruta_emg[:-len("_emg.parquet")] if ruta_emg.endswith("_emg.parquet") else ruta_emg.rsplit(".", 1)[0]
nombre_salida_html = f"{prefijo}_analisis_cortocircuito.html"

tabla_emg = pd.read_parquet(ruta_emg)
print(tabla_emg)

# paquete_id (si existe) es el numero de secuencia del paquete BLE, no un canal EMG.
canales_emg = [c for c in tabla_emg.columns if c != "paquete_id"]

FRECUENCIA_MUESTREO = 2000
tiempo_emg = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

canales_uv = {c: tabla_emg[c].to_numpy(dtype=float) * LSB_UV for c in canales_emg}
rango_maximo = max(m.max() - m.min() for m in canales_uv.values())
paso_desplazamiento = rango_maximo * 1.2 if rango_maximo > 0 else 1.0

fig = go.Figure()
for indice, columna in enumerate(canales_emg):
    # ch1 arriba del todo, ch8 abajo del todo: al primero de la lista le
    # corresponde el desplazamiento mas alto, no el mas bajo.
    posicion = len(canales_emg) - 1 - indice
    fig.add_trace(go.Scatter(
        x=tiempo_emg, y=canales_uv[columna] + posicion * paso_desplazamiento, mode="lines", name=columna,
        customdata=canales_uv[columna],  # valor real en uV, sin el desplazamiento de dibujo
        hovertemplate="tiempo=%{x:.2f}s<br>%{customdata:.1f} µV<extra>" + columna + "</extra>",
    ))
fig.update_layout(
    title=f"Señal en el tiempo (µV) - {ruta_emg}",
    xaxis_title="tiempo (s)",
    yaxis_title="Valor de tensión (µV)",
)

fig.write_html(nombre_salida_html)
print(f"Grafica guardada en {nombre_salida_html}")
fig.show()

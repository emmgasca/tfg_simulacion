# Inspeccion visual rapida de una captura ya guardada: dibuja los 8
# canales EMG (y el IMU, si existe) en una grafica interactiva HTML.
# No filtra ni analiza nada -- para eso estan snr_diagnostico.py y
# snr_limpieza.py.
#
# Uso: python analizar.py [nombre_emg.parquet]
# Sin argumentos, usa captura_emg.parquet (como antes). El HTML se guarda
# con el mismo prefijo que el parquet de entrada, para no pisar el de otra
# captura (p. ej. prueba_emg.parquet -> prueba_analisis.html).
import sys

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ruta_emg = sys.argv[1] if len(sys.argv) > 1 else "captura_emg.parquet"
prefijo = ruta_emg[:-len("_emg.parquet")] if ruta_emg.endswith("_emg.parquet") else ruta_emg.rsplit(".", 1)[0]
ruta_imu = f"{prefijo}_imu.parquet"
nombre_salida_html = f"{prefijo}_analisis.html"

tabla_emg = pd.read_parquet(ruta_emg)
print(tabla_emg)

# paquete_id (si existe) es el numero de secuencia del paquete BLE, no un canal EMG.
canales_emg = [c for c in tabla_emg.columns if c != "paquete_id"]

FRECUENCIA_MUESTREO = 2000
tiempo_emg = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

try:
    tabla_imu = pd.read_parquet(ruta_imu)
except FileNotFoundError:
    tabla_imu = None

if tabla_imu is not None and len(tabla_imu) > 0:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("EMG (8 canales)", "IMU (x, y, z)"),
    )
    for columna in canales_emg:
        fig.add_trace(go.Scatter(x=tiempo_emg, y=tabla_emg[columna], mode="lines", name=columna), row=1, col=1)
    for eje in ("x", "y", "z"):
        fig.add_trace(go.Scatter(x=tabla_imu["t"], y=tabla_imu[eje], mode="lines", name=f"imu_{eje}"), row=2, col=1)
    fig.update_yaxes(title_text="valor EMG", row=1, col=1)
    fig.update_yaxes(title_text="IMU", row=2, col=1)
    fig.update_xaxes(title_text="tiempo (s)", row=2, col=1)
    fig.update_layout(title=f"Señal capturada - EMG + IMU ({ruta_emg})")
else:
    fig = go.Figure()
    for columna in canales_emg:
        fig.add_trace(go.Scatter(x=tiempo_emg, y=tabla_emg[columna], mode="lines", name=columna))
    fig.update_layout(
        title=f"Señal capturada - 8 canales ({ruta_emg})",
        xaxis_title="tiempo (s)",
        yaxis_title="valor EMG",
    )

fig.write_html(nombre_salida_html)
print(f"Grafica guardada en {nombre_salida_html}")
fig.show()

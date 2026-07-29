import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

tabla_emg = pd.read_parquet("captura_emg.parquet")
print(tabla_emg)

# paquete_id (si existe) es el numero de secuencia del paquete BLE, no un canal EMG.
canales_emg = [c for c in tabla_emg.columns if c != "paquete_id"]

FRECUENCIA_MUESTREO = 2000
tiempo_emg = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

try:
    tabla_imu = pd.read_parquet("captura_imu.parquet")
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
    fig.update_layout(title="Señal capturada - EMG + IMU")
else:
    fig = go.Figure()
    for columna in canales_emg:
        fig.add_trace(go.Scatter(x=tiempo_emg, y=tabla_emg[columna], mode="lines", name=columna))
    fig.update_layout(
        title="Señal capturada - 8 canales",
        xaxis_title="tiempo (s)",
        yaxis_title="valor EMG",
    )

fig.write_html("C:/Users/emmag/Documents/PlatformIO/Projects/TFG_simulacion/A.html")
fig.show()
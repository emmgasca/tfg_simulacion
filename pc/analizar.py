import pandas as pd
import numpy as np
import plotly.graph_objects as go

tabla_emg = pd.read_parquet("captura_emg.parquet")
print(tabla_emg)

FRECUENCIA_MUESTREO = 2000
tiempo = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

fig = go.Figure()

for columna in tabla_emg.columns:
    fig.add_trace(go.Scatter(x=tiempo, y=tabla_emg[columna], mode="lines", name=columna))

fig.update_layout(
    title="Señal capturada - 8 canales",
    xaxis_title="tiempo (s)",
    yaxis_title="valor EMG"
)

fig.write_html("C:/Users/emmag/Documents/PlatformIO/Projects/TFG_simulacion/A.html")
fig.show()
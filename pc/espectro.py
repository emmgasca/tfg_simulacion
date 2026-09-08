# Dibuja el espectro de ruido en cortocircuito, estilo Fig. 4(c) del
# paper Myolink: los 8 canales sueltos (finos, uno por color) mas la
# mediana entre ellos (linea negra gruesa, "Sistema propio") frente a la
# linea de referencia de Myolink, todo en escala log-log.
#
# Reutiliza el calculo de irn.py (misma funcion calcular_irn), asi que da
# el mismo resultado que la grafica de espectro que genera irn.py, pero
# como script aparte que abre la grafica directamente al ejecutarlo, sin
# tener que pasar por el resto de graficas ni por la comparacion con una
# señal EMG real.
#
# Uso: python espectro.py [nombre_emg.parquet]
# Sin argumentos, usa cortocircuito_emg.parquet.
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from irn import calcular_irn, FRECUENCIA_MUESTREO, MYOLINK_ASD_MEDIANA_NV

ruta = sys.argv[1] if len(sys.argv) > 1 else "cortocircuito_emg.parquet"
tabla_emg = pd.read_parquet(ruta)

frecuencias_por_canal, espectros, irn = calcular_irn(tabla_emg)
canales_validos = [c for c, v in irn.items() if v["irn_rms_uv"] == v["irn_rms_uv"]]

fig = go.Figure()

# Los 8 canales sueltos primero (finos), para que la mediana se dibuje
# encima y quede bien visible, no tapada por las lineas de cada canal.
for canal, asd_nv in espectros.items():
    v = irn[canal]
    etiqueta = f"{canal} (SATURADO {v['saturado_pct']:.0f}%)" if v["irn_rms_uv"] != v["irn_rms_uv"] else canal
    fig.add_trace(go.Scatter(x=frecuencias_por_canal[canal], y=asd_nv, mode="lines", name=etiqueta, line=dict(width=1)))

if canales_validos:
    f_comun = np.linspace(1, FRECUENCIA_MUESTREO / 2, 500)
    espectros_interpolados = [
        np.interp(f_comun, frecuencias_por_canal[c], espectros[c]) for c in canales_validos
    ]
    mediana_sistema = np.median(espectros_interpolados, axis=0)
    mediana_valor = float(np.median(mediana_sistema))

    fig.add_trace(go.Scatter(x=f_comun, y=mediana_sistema, mode="lines", name="Sistema propio (mediana)", line=dict(width=3, color="black")))
    fig.add_hline(
        y=mediana_valor, line_dash="dash",
        annotation_text=f"Sistema propio: {mediana_valor:.0f} nV/sqrt(Hz) mediana",
    )
else:
    print("Aviso: ningun canal valido, no se puede calcular la linea del sistema propio.")

# Como traza (no add_hline) para que aparezca en la leyenda, no solo
# como anotacion sobre la grafica.
fig.add_trace(go.Scatter(
    x=[1, 1000], y=[MYOLINK_ASD_MEDIANA_NV, MYOLINK_ASD_MEDIANA_NV], mode="lines",
    line=dict(dash="dash", color="red"),
    name=f"Myolink (paper): {MYOLINK_ASD_MEDIANA_NV:.0f} nV/sqrt(Hz) mediana",
))
# exponentformat="power": mismo estilo de notacion que el paper (10^0,
# 10^1, 10^2...), en vez de la mezcla de sufijos (k, M, B, T) que pone
# Plotly por defecto cuando el rango de valores es muy grande.
fig.update_xaxes(type="log", dtick=1, exponentformat="power", title_text="Frecuencia (Hz)", range=[0, 3])  # 1 a 1000 Hz, igual que Fig. 4c
fig.update_yaxes(type="log", dtick=1, exponentformat="power", title_text="Densidad de ruido (nV/sqrt(Hz))", range=[0, 8])
fig.update_layout(title=f"Espectro de ruido en cortocircuito, estilo Myolink Fig. 4(c) - {ruta}")

prefijo = ruta[:-len("_emg.parquet")] if ruta.endswith("_emg.parquet") else ruta.rsplit(".", 1)[0]
nombre_html = f"{prefijo}_espectro.html"
fig.write_html(nombre_html)
print(f"Grafica guardada en {nombre_html}")

fig.show()

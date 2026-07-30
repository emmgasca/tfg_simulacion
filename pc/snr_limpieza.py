# snr_limpieza: filtra de verdad la señal EMG (paso-banda + notch de red)
# y guarda la version limpia. Para solo medir el SNR sin tocar la senal,
# usar snr_diagnostico.py.

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import butter, filtfilt, iirnotch

from snr_diagnostico import BANDA_SENAL_HZ, RUIDO_HZ, FRECUENCIA_MUESTREO, calcular_snr

ORDEN_PASABANDA = 4       # Butterworth 4o orden, igual que en Myolink
ANCHO_NOTCH_Q = 30.0      # factor Q del notch: cuanto mas alto, mas estrecho el rechazo


def disenar_pasabanda(banda_hz=BANDA_SENAL_HZ, fs=FRECUENCIA_MUESTREO, orden=ORDEN_PASABANDA):
    nyquist = fs / 2.0
    baja = banda_hz[0] / nyquist
    alta = banda_hz[1] / nyquist
    return butter(orden, [baja, alta], btype="bandpass")


def limpiar_senal(muestras, fs=FRECUENCIA_MUESTREO):
    b, a = disenar_pasabanda(fs=fs)
    limpia = filtfilt(b, a, muestras)

    for armonico in RUIDO_HZ:
        b_notch, a_notch = iirnotch(armonico, ANCHO_NOTCH_Q, fs)
        limpia = filtfilt(b_notch, a_notch, limpia)

    return limpia


def limpiar_tabla(tabla_emg, fs=FRECUENCIA_MUESTREO):
    tabla_limpia = pd.DataFrame(index=tabla_emg.index)
    for columna in tabla_emg.columns:
        if columna == "paquete_id":
            # No es una señal EMG: se copia tal cual, sin filtrar, para poder
            # seguir analizando huecos de secuencia sobre la señal limpia.
            tabla_limpia[columna] = tabla_emg[columna]
            continue
        muestras = tabla_emg[columna].to_numpy(dtype=float)
        tabla_limpia[columna] = limpiar_senal(muestras, fs=fs)
    return tabla_limpia


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "captura_emg.parquet"
    tabla_emg = pd.read_parquet(ruta)

    print(f"Archivo: {ruta}")
    print(f"Fs asumida: {FRECUENCIA_MUESTREO} Hz")

    snr_antes = calcular_snr(tabla_emg)
    tabla_limpia = limpiar_tabla(tabla_emg)
    snr_despues = calcular_snr(tabla_limpia)

    for canal in tabla_emg.columns:
        if canal == "paquete_id":
            continue
        print(f"{canal}: SNR antes = {snr_antes[canal]:.1f} dB -> "
              f"SNR despues = {snr_despues[canal]:.1f} dB")

    prefijo = ruta[:-len("_emg.parquet")] if ruta.endswith("_emg.parquet") else ruta.rsplit(".", 1)[0]
    nombre_salida_parquet = f"{prefijo}_limpio.parquet"
    nombre_salida_html = f"{prefijo}_limpio.html"

    tabla_limpia.to_parquet(nombre_salida_parquet)
    print(f"Senal limpia guardada en {nombre_salida_parquet}")

    tiempo = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("EMG original", "EMG filtrada (pasa-banda + notch)"),
    )
    for columna in tabla_emg.columns:
        if columna == "paquete_id":
            continue
        fig.add_trace(go.Scatter(x=tiempo, y=tabla_emg[columna], mode="lines", name=columna), row=1, col=1)
    for columna in tabla_limpia.columns:
        if columna == "paquete_id":
            continue
        fig.add_trace(go.Scatter(x=tiempo, y=tabla_limpia[columna], mode="lines", name=f"{columna}_limpio"), row=2, col=1)
    fig.update_xaxes(title_text="tiempo (s)", row=2, col=1)
    fig.update_layout(title=f"Limpieza EMG - {ruta}")

    fig.write_html(nombre_salida_html)
    print(f"Grafica guardada en {nombre_salida_html}")
    fig.show()

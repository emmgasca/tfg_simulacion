
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

FRECUENCIA_MUESTREO = 1458  # Hz 

RUIDO_HZ = (50, 100, 150, 200)  # red electrica y armonicos
ANCHO_NOTCH_HZ = 2.0            # +/- Hz alrededor de cada armonico considerado "ruido"
BANDA_SENAL_HZ = (20.0, 450.0)  # banda fisiologica tipica de EMG de superficie


def calcular_snr(tabla_emg, fs=FRECUENCIA_MUESTREO):
    n = len(tabla_emg)
    ventana = np.hanning(n) #atenua fugas espectrales
    frecuencias = np.fft.rfftfreq(n, d=1.0 / fs) #vector de frecuencias para la FFT real

    en_banda_senal = (frecuencias >= BANDA_SENAL_HZ[0]) & (frecuencias <= BANDA_SENAL_HZ[1])
    en_ruido = np.zeros_like(en_banda_senal)
    for armonico in RUIDO_HZ:
        en_ruido |= np.abs(frecuencias - armonico) <= ANCHO_NOTCH_HZ

    resultados = {}
    for columna in tabla_emg.columns: #itera cada canal EMG
        muestras = tabla_emg[columna].to_numpy(dtype=float) #extrae la columna como array
        muestras = muestras - muestras.mean()  # quita offset DC, centra la señal en cero
        espectro = np.fft.rfft(muestras * ventana) #aplica la ventana y calcula la FFT real
        potencia = np.abs(espectro) ** 2 #densidad de potencia

        potencia_ruido = potencia[en_banda_senal & en_ruido].sum()
        potencia_senal = potencia[en_banda_senal & ~en_ruido].sum()

        if potencia_ruido == 0:
            resultados[columna] = float("inf")
        else:
            resultados[columna] = 10 * np.log10(potencia_senal / potencia_ruido)

    return resultados


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "captura_snr.parquet"
    tabla_emg = pd.read_parquet(ruta)
    snr = calcular_snr(tabla_emg)
    print(f"Archivo: {ruta}")
    print(f"Fs asumida: {FRECUENCIA_MUESTREO} Hz") #debe coincidir con analizar.py
    for canal, valor in snr.items():
        print(f"{canal}: SNR = {valor:.1f} dB (senal {BANDA_SENAL_HZ} Hz vs. red {RUIDO_HZ} Hz)")

    tabla_snr = pd.DataFrame(list(snr.items()), columns=["canal", "snr_db"])
    tabla_snr.to_parquet("snr.parquet")
    print("Guardado en snr.parquet")

    fig = go.Figure(go.Bar(x=tabla_snr["canal"], y=tabla_snr["snr_db"]))
    fig.update_layout(
        title=f"SNR por canal - {ruta}",
        xaxis_title="canal",
        yaxis_title="SNR (dB)",
    )
    fig.write_html("snr.html")
    fig.show()

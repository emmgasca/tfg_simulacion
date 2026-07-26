"""Calcula el SNR de cada canal EMG respecto al ruido de red electrica (50 Hz).

Idea general (sin entrar en detalle aun): la señal capturada mezcla la
actividad muscular real con el zumbido de la red electrica (50 Hz y sus
multiplos: 100, 150, 200 Hz). Para separar cuanto hay de cada cosa, se
convierte la señal de "voltaje a lo largo del tiempo" a "energia por cada
frecuencia" (FFT), y simplemente se suma la energia que cae justo en esas
frecuencias de red (ruido) frente a la energia del resto de la banda donde
vive el EMG real (señal).

SNR_dB = 10 * log10(potencia_senal / potencia_ruido)
"""

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Debe coincidir con analizar.py y con la tasa real que configura CONFIG1 en el ADS1298.
FRECUENCIA_MUESTREO = 2000  # Hz

RUIDO_HZ = (50, 100, 150, 200)  # 50 Hz de la red electrica y sus armonicos
ANCHO_NOTCH_HZ = 2.0            # se considera "ruido" un margen de +/- 2 Hz alrededor de cada uno
BANDA_SENAL_HZ = (20.0, 450.0)  # banda fisiologica tipica de EMG de superficie


def calcular_snr(tabla_emg, fs=FRECUENCIA_MUESTREO):
    n = len(tabla_emg)

    # Ventana de Hann: suaviza el principio y el final de la señal antes de la
    # FFT (como un fundido de entrada/salida). Sin esto, el corte brusco al
    # inicio/fin de la grabación "gotea" energia falsa hacia frecuencias
    # vecinas y contamina la medida.
    ventana = np.hanning(n)

    # A que frecuencia (en Hz) corresponde cada punto del resultado de la FFT,
    # dado el numero de muestras y la frecuencia de muestreo.
    frecuencias = np.fft.rfftfreq(n, d=1.0 / fs)

    # Dos "mascaras" booleanas, una por cada frecuencia: ¿es banda de señal
    # EMG? ¿es banda de ruido de red?
    en_banda_senal = (frecuencias >= BANDA_SENAL_HZ[0]) & (frecuencias <= BANDA_SENAL_HZ[1])
    en_ruido = np.zeros_like(en_banda_senal)
    for armonico in RUIDO_HZ:
        en_ruido |= np.abs(frecuencias - armonico) <= ANCHO_NOTCH_HZ

    resultados = {}
    for columna in tabla_emg.columns:
        muestras = tabla_emg[columna].to_numpy(dtype=float)
        muestras = muestras - muestras.mean()  # quita el offset DC antes de la FFT

        espectro = np.fft.rfft(muestras * ventana)  # voltaje -> energia por frecuencia
        potencia = np.abs(espectro) ** 2

        # Suma la energia en cada mascara y calcula el ratio en decibelios.
        potencia_ruido = potencia[en_banda_senal & en_ruido].sum()
        potencia_senal = potencia[en_banda_senal & ~en_ruido].sum()

        if potencia_ruido == 0:
            resultados[columna] = float("inf")
        else:
            resultados[columna] = 10 * np.log10(potencia_senal / potencia_ruido)

    return resultados


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "captura_emg.parquet"
    tabla_emg = pd.read_parquet(ruta)
    snr = calcular_snr(tabla_emg)

    print(f"Archivo: {ruta}")
    print(f"Fs asumida: {FRECUENCIA_MUESTREO} Hz (debe coincidir con analizar.py)")
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

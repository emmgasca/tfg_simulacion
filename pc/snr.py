"""Estima el SNR de cada canal EMG respecto al ruido de red electrica.

Definicion usada: dentro de la banda fisiologica de EMG de superficie
(20-450 Hz), se separa la potencia espectral en dos partes:
  - "ruido": bandas estrechas alrededor de 50 Hz y sus armonicos (100, 150, 200 Hz)
  - "senal": el resto de la banda fisiologica

SNR_dB = 10 * log10(potencia_senal / potencia_ruido)

Si tu TFG necesita otra definicion (p.ej. relativa a una captura de
"reposo" sin contraccion muscular), avisa y se ajusta.
"""

import numpy as np
import pandas as pd

from config_captura import FRECUENCIA_MUESTREO_EMG

RUIDO_HZ = (50, 100, 150, 200)  # red electrica y armonicos
ANCHO_NOTCH_HZ = 2.0            # +/- Hz alrededor de cada armonico considerado "ruido"
BANDA_SENAL_HZ = (20.0, 450.0)  # banda fisiologica tipica de EMG de superficie


def calcular_snr(tabla_emg, fs=FRECUENCIA_MUESTREO_EMG):
    n = len(tabla_emg)
    frecuencias = np.fft.rfftfreq(n, d=1.0 / fs)

    en_banda_senal = (frecuencias >= BANDA_SENAL_HZ[0]) & (frecuencias <= BANDA_SENAL_HZ[1])
    en_ruido = np.zeros_like(en_banda_senal)
    for armonico in RUIDO_HZ:
        en_ruido |= np.abs(frecuencias - armonico) <= ANCHO_NOTCH_HZ

    resultados = {}
    for columna in tabla_emg.columns:
        espectro = np.fft.rfft(tabla_emg[columna].to_numpy(dtype=float))
        potencia = np.abs(espectro) ** 2

        potencia_ruido = potencia[en_banda_senal & en_ruido].sum()
        potencia_senal = potencia[en_banda_senal & ~en_ruido].sum()

        if potencia_ruido == 0:
            resultados[columna] = float("inf")
        else:
            resultados[columna] = 10 * np.log10(potencia_senal / potencia_ruido)

    return resultados


if __name__ == "__main__":
    tabla_emg = pd.read_parquet("captura_emg.parquet")
    snr = calcular_snr(tabla_emg)
    print(f"Fs asumida: {FRECUENCIA_MUESTREO_EMG} Hz (verifica contra el log de Serial)")
    for canal, valor in snr.items():
        print(f"{canal}: SNR = {valor:.1f} dB (senal {BANDA_SENAL_HZ} Hz vs. red {RUIDO_HZ} Hz)")

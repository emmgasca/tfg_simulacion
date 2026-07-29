# snr_diagnostico: mide el SNR de una captura EMG SIN modificar la señal.
# Para limpiar de verdad la señal (filtro paso-banda + notch), usar snr_limpieza.py.

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

FRECUENCIA_MUESTREO = 2000  # Hz -- debe coincidir con analizar.py y CONFIG1 del ADS1298

RUIDO_HZ = (50, 100, 150, 200)  # red electrica y armonicos
ANCHO_NOTCH_HZ = 2.0            # +/- Hz alrededor de cada armonico considerado "ruido"
BANDA_SENAL_HZ = (20.0, 450.0)  # banda fisiologica tipica de EMG de superficie


def calcular_snr(tabla_emg, fs=FRECUENCIA_MUESTREO):
    n = len(tabla_emg)
    ventana = np.hanning(n)
    frecuencias = np.fft.rfftfreq(n, d=1.0 / fs)

    en_banda_senal = (frecuencias >= BANDA_SENAL_HZ[0]) & (frecuencias <= BANDA_SENAL_HZ[1])
    en_ruido = np.zeros_like(en_banda_senal)
    for armonico in RUIDO_HZ:
        en_ruido |= np.abs(frecuencias - armonico) <= ANCHO_NOTCH_HZ

    resultados = {}
    # paquete_id (si existe) es el numero de secuencia del paquete BLE, no un canal EMG.
    for columna in tabla_emg.columns:
        if columna == "paquete_id":
            continue
        muestras = tabla_emg[columna].to_numpy(dtype=float)
        muestras = muestras - muestras.mean()  # quitar offset DC antes de ventanear/FFT
        espectro = np.fft.rfft(muestras * ventana)
        potencia = np.abs(espectro) ** 2

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

    prefijo = ruta[:-len("_emg.parquet")] if ruta.endswith("_emg.parquet") else ruta.rsplit(".", 1)[0]
    nombre_salida_parquet = f"{prefijo}_snr.parquet"
    nombre_salida_html = f"{prefijo}_snr.html"

    tabla_snr = pd.DataFrame(list(snr.items()), columns=["canal", "snr_db"])
    tabla_snr.to_parquet(nombre_salida_parquet)
    print(f"Guardado en {nombre_salida_parquet}")

    fig = go.Figure(go.Bar(x=tabla_snr["canal"], y=tabla_snr["snr_db"]))
    fig.update_layout(
        title=f"SNR por canal - {ruta}",
        xaxis_title="canal",
        yaxis_title="SNR (dB)",
    )
    fig.write_html(nombre_salida_html)
    print(f"Grafica guardada en {nombre_salida_html}")
    fig.show()

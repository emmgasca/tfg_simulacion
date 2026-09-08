# Recorre una carpeta con capturas guardadas (pares *_emg.parquet / *_imu.parquet)
# y para cada una genera la misma grafica que analizar.py, pero aplicando antes
# un filtro paso-banda 15-450 Hz, un notch en 50 Hz y sus armonicos (100, 150,
# 200... Hz), y una referencia promedio comun (se resta la media de todos los
# canales a cada canal) sobre los canales EMG. El IMU no se filtra.
#
# Uso: python analizar_filtrado.py [carpeta]
# Sin argumentos, usa C:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\pc
import glob
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import butter, filtfilt, iirnotch

FRECUENCIA_MUESTREO = 2000     # Hz -- debe coincidir con CONFIG1 del ADS1298
BANDA_PASO_HZ = (15.0, 450.0)  # filtro paso-banda pedido
ORDEN_PASABANDA = 4            # Butterworth 4o orden, igual que en snr_limpieza.py
ANCHO_NOTCH_Q = 30.0           # factor Q del notch: cuanto mas alto, mas estrecho el rechazo

# Armonicos de la red electrica (50 Hz) por debajo de Nyquist
ARMONICOS_50HZ = list(range(50, FRECUENCIA_MUESTREO // 2, 50))


def disenar_pasabanda(banda_hz=BANDA_PASO_HZ, fs=FRECUENCIA_MUESTREO, orden=ORDEN_PASABANDA):
    nyquist = fs / 2.0
    baja = banda_hz[0] / nyquist
    alta = banda_hz[1] / nyquist
    return butter(orden, [baja, alta], btype="bandpass")


def filtrar_senal(muestras, fs=FRECUENCIA_MUESTREO):
    b, a = disenar_pasabanda(fs=fs)
    filtrada = filtfilt(b, a, muestras)

    for armonico in ARMONICOS_50HZ:
        b_notch, a_notch = iirnotch(armonico, ANCHO_NOTCH_Q, fs)
        filtrada = filtfilt(b_notch, a_notch, filtrada)

    return filtrada


def filtrar_tabla(tabla_emg, fs=FRECUENCIA_MUESTREO):
    tabla_filtrada = pd.DataFrame(index=tabla_emg.index)
    for columna in tabla_emg.columns:
        if columna == "paquete_id":
            # No es una senal EMG: se copia tal cual.
            tabla_filtrada[columna] = tabla_emg[columna]
            continue
        muestras = tabla_emg[columna].to_numpy(dtype=float)
        tabla_filtrada[columna] = filtrar_senal(muestras, fs=fs)
    return tabla_filtrada


def restar_referencia_promedio(tabla_filtrada, canales_emg):
    # Referencia promedio comun (CAR): a cada canal se le resta, muestra a
    # muestra, la media de todos los canales EMG. Sirve para atenuar ruido
    # que entra por igual en todos los canales (p. ej. interferencia de red
    # residual o modo comun).
    tabla_referenciada = tabla_filtrada.copy()
    media_canales = tabla_filtrada[canales_emg].mean(axis=1)
    for columna in canales_emg:
        tabla_referenciada[columna] = tabla_filtrada[columna] - media_canales
    return tabla_referenciada


def procesar_captura(ruta_emg):
    prefijo = ruta_emg[:-len("_emg.parquet")] if ruta_emg.endswith("_emg.parquet") else ruta_emg.rsplit(".", 1)[0]
    ruta_imu = f"{prefijo}_imu.parquet"
    nombre_salida_html = f"{prefijo}_analisis_filtrado.html"
    nombre_salida_csv = f"{prefijo}_filtrado.csv"

    tabla_emg = pd.read_parquet(ruta_emg)
    if len(tabla_emg) == 0:
        print(f"  [omitido] {ruta_emg} esta vacio")
        return

    canales_emg = [c for c in tabla_emg.columns if c != "paquete_id"]
    tabla_filtrada = filtrar_tabla(tabla_emg)
    tabla_filtrada = restar_referencia_promedio(tabla_filtrada, canales_emg)
    tiempo_emg = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

    tabla_csv = tabla_filtrada.copy()
    tabla_csv.insert(0, "tiempo", tiempo_emg)
    tabla_csv.to_csv(nombre_salida_csv, index=False)
    print(f"  Datos filtrados guardados en {nombre_salida_csv}")

    try:
        tabla_imu = pd.read_parquet(ruta_imu)
    except FileNotFoundError:
        tabla_imu = None

    if tabla_imu is not None and len(tabla_imu) > 0:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            subplot_titles=("EMG filtrada (paso-banda + notch + ref. promedio comun)", "IMU (x, y, z)"),
        )
        for columna, bias in zip(canales_emg, range(len(canales_emg))):
            fig.add_trace(go.Scatter(x=tiempo_emg, y=tabla_filtrada[columna] + bias * 2000000, mode="lines", name=columna), row=1, col=1)
        for eje in ("x", "y", "z"):
            fig.add_trace(go.Scatter(x=tabla_imu["t"], y=tabla_imu[eje], mode="lines", name=f"imu_{eje}"), row=2, col=1)
        fig.update_yaxes(title_text="valor EMG", row=1, col=1)
        fig.update_yaxes(title_text="IMU", row=2, col=1)
        fig.update_xaxes(title_text="tiempo (s)", row=2, col=1)
        fig.update_layout(title=f"Señal filtrada - EMG + IMU ({ruta_emg})")
    else:
        fig = go.Figure()
        for columna, bias in zip(canales_emg, range(len(canales_emg))):
            fig.add_trace(go.Scatter(x=tiempo_emg, y=tabla_filtrada[columna] + bias * 200000, mode="lines", name=columna))
        fig.update_layout(
            title=f"Señal filtrada - 8 canales ({ruta_emg})",
            xaxis_title="tiempo (s)",
            yaxis_title="valor EMG",
        )

    fig.write_html(nombre_salida_html)
    print(f"  Grafica guardada en {nombre_salida_html}")


if __name__ == "__main__":
    carpeta = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\pc"

    rutas_emg = sorted(glob.glob(os.path.join(carpeta, "*_emg.parquet")))
    if not rutas_emg:
        print(f"No se encontraron ficheros *_emg.parquet en {carpeta}")
        sys.exit(1)

    print(f"Filtro paso-banda: {BANDA_PASO_HZ} Hz -- Notch en: {ARMONICOS_50HZ} Hz")
    print(f"Encontradas {len(rutas_emg)} capturas EMG en {carpeta}")

    for ruta_emg in rutas_emg:
        print(f"Procesando {ruta_emg}")
        try:
            procesar_captura(ruta_emg)
        except Exception as error:
            print(f"  [error] {error}")

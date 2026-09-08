# irn.py: mide el ruido referido a la entrada (IRN) exactamente igual que
# el paper Myolink (Koutsoftidis et al., IEEE TBME 2022), seccion II.F:
#
#   "The IRN was measured by shorting both working and reference INA
#    inputs to system ground and recording the ADC output at 2 kHz for
#    10 seconds."
#
# El paper calcula el espectro de ruido SIN filtrar la senal (ver pie de
# la Fig. 4c: "without digital filtering applied"), y luego integra ese
# espectro en la banda 23-524 Hz para dar el resultado final en uVrms
# (384 nVrms para Myolink). Este script hace lo mismo: no aplica ningun
# filtro paso-banda a la senal, solo calcula el espectro de densidad de
# potencia (PSD, metodo de Welch) y lo integra en la banda de interes.
#
# Factor de conversion cuentas ADC -> voltios, verificado contra el
# firmware real (ads1298.cpp) y la Tabla 18/20 del datasheet SBAS459K:
#   CONFIG3 = 0b11001001 -> VREF_4V = 0 -> VREF = 2.4 V
#   CHnSET  = 0x00        -> GAINn = 000 -> Gain = 6
#   LSB = 2*VREF / (Gain * 2**24)

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.signal import welch

FRECUENCIA_MUESTREO = 2000  # Hz -- confirmado: CONFIG1=0x84, HR=1, DR=100 -> 2 kSPS

VREF = 2.4  # V, confirmado con CONFIG3 (VREF_4V=0)
GANANCIA_PGA = 6  # PGA interno del ADS1298, confirmado con CHnSET (GAINn=000)
GANANCIA_AFE = 10  # INA333, 20 dB fijos, ver capitulo 2 subsubsec:afe_etapa
GANANCIA = GANANCIA_PGA * GANANCIA_AFE  # ganancia total electrodo -> codigo ADC
# OJO: usar la ganancia TOTAL (AFE x PGA), no solo la PGA, para que el
# resultado quede referido al electrodo (definicion real de IRN, la misma
# que usa el paper Myolink). Dividir solo por la PGA da el ruido a la
# SALIDA del AFE (entrada del ADS1298), no el ruido de entrada real.
LSB_V = (2 * VREF) / (GANANCIA * 2**24)  # voltios por cuenta ADC, referidos al electrodo
LSB_UV = LSB_V * 1e6  # microvoltios por cuenta ADC

BANDA_IRN_HZ = (23.0, 524.0)  # misma banda que usa el paper para poder comparar

CUENTA_MAX = 2**23 - 1   # 8388607, tope positivo del ADC (24 bits con signo)
CUENTA_MIN = -(2**23)    # -8388608, tope negativo
UMBRAL_SATURACION = 0.001  # si >0.1% de las muestras tocan el tope, el canal esta saturado
DURACION_MINIMA_VENTANA_S = 1.0  # ventana minima para poder calcular un espectro fiable

# Valores publicados en el paper (Fig. 4c / Tabla II), solo como referencia visual.
MYOLINK_IRN_RMS_UV = 0.384
MYOLINK_ASD_MEDIANA_NV = 18.0


def cuentas_a_uv(muestras_cuentas):
    return muestras_cuentas.astype(float) * LSB_UV


def fraccion_saturada(muestras_cuentas):
    """Cuantas muestras del canal estan pegadas a un tope del ADC (0 a 1)."""
    en_tope = (muestras_cuentas == CUENTA_MAX) | (muestras_cuentas == CUENTA_MIN)
    return en_tope.mean()


def racha_mas_larga(mascara_saturado):
    """(inicio, fin) de la racha continua mas larga de muestras NO saturadas.

    Si un canal esta saturado la mayor parte de la grabacion (por ejemplo,
    porque solo se cortocircuito unos segundos dentro de una captura mas
    larga), esto encuentra el tramo de tiempo en el que si estuvo limpio,
    para poder calcular el IRN solo ahi en vez de descartar el canal entero.
    Devuelve (-1, -1) si no hay ninguna muestra sin saturar.
    """
    mejor_inicio = mejor_fin = -1
    mejor_len = 0
    actual_inicio = None
    for i, saturada in enumerate(mascara_saturado):
        if not saturada and actual_inicio is None:
            actual_inicio = i
        elif saturada and actual_inicio is not None:
            if i - actual_inicio > mejor_len:
                mejor_len = i - actual_inicio
                mejor_inicio, mejor_fin = actual_inicio, i
            actual_inicio = None
    if actual_inicio is not None and len(mascara_saturado) - actual_inicio > mejor_len:
        mejor_inicio, mejor_fin = actual_inicio, len(mascara_saturado)
    return mejor_inicio, mejor_fin


def calcular_espectro(señal_uv, fs):
    señal_uv = señal_uv - señal_uv.mean()  # quitar offset DC, no es ruido
    nperseg = min(len(señal_uv), fs)  # ventanas de 1s -> resolucion de 1Hz
    frecuencias, psd = welch(señal_uv, fs=fs, nperseg=nperseg, scaling="density")
    return frecuencias, psd  # psd en (uV)^2/Hz porque señal_uv ya esta en uV


def calcular_irn(tabla_emg, fs=FRECUENCIA_MUESTREO, banda_hz=BANDA_IRN_HZ):
    """Para cada canal: espectro (ASD, nV/sqrt(Hz)) y ruido RMS integrado en la banda (uV).

    Sin filtrar la senal en ningun momento, igual que el paper: solo se
    quita el offset DC antes de calcular el espectro (Welch), y se integra
    la potencia dentro de la banda de interes.

    Si el canal esta saturado mas del umbral en TODA la grabacion, se busca
    automaticamente la racha continua mas larga sin saturar (por ejemplo el
    tramo en el que se mantuvo cortocircuitado a mano) y se calcula el IRN
    solo sobre esa ventana, en vez de descartar el canal entero. El inicio y
    fin de esa ventana (en segundos) se guarda en el resultado para dejar
    constancia de que no es la grabacion completa.
    """
    resultados = {}
    espectros = {}
    frecuencias_por_canal = {}

    for columna in tabla_emg.columns:
        if columna == "paquete_id":
            continue
        cuentas_completas = tabla_emg[columna].to_numpy()
        saturado_total = fraccion_saturada(cuentas_completas)
        ventana_s = None
        cuentas = cuentas_completas

        if saturado_total > UMBRAL_SATURACION:
            en_tope = (cuentas_completas == CUENTA_MAX) | (cuentas_completas == CUENTA_MIN)
            inicio, fin = racha_mas_larga(en_tope)
            duracion = (fin - inicio) / fs if inicio != -1 else 0.0

            if inicio == -1 or duracion < DURACION_MINIMA_VENTANA_S:
                # Ni un tramo limpio suficientemente largo: se descarta,
                # pero el espectro se calcula igual sobre todo el archivo
                # para poder verlo en la grafica comparativa.
                frecuencias, psd = calcular_espectro(cuentas_a_uv(cuentas_completas), fs)
                frecuencias_por_canal[columna] = frecuencias
                espectros[columna] = np.sqrt(psd) * 1000
                resultados[columna] = {
                    "irn_rms_uv": float("nan"),
                    "saturado_pct": saturado_total * 100,
                    "ventana_inicio_s": None,
                    "ventana_fin_s": None,
                }
                continue

            cuentas = cuentas_completas[inicio:fin]
            ventana_s = (inicio / fs, fin / fs)

        frecuencias, psd = calcular_espectro(cuentas_a_uv(cuentas), fs)
        frecuencias_por_canal[columna] = frecuencias
        espectros[columna] = np.sqrt(psd) * 1000  # uV/sqrt(Hz) -> nV/sqrt(Hz)

        en_banda = (frecuencias >= banda_hz[0]) & (frecuencias <= banda_hz[1])
        irn_rms = np.sqrt(np.trapezoid(psd[en_banda], frecuencias[en_banda]))  # uV

        resultados[columna] = {
            "irn_rms_uv": irn_rms,
            "saturado_pct": saturado_total * 100,  # saturacion del ARCHIVO COMPLETO, no de la ventana
            "ventana_inicio_s": ventana_s[0] if ventana_s else None,
            "ventana_fin_s": ventana_s[1] if ventana_s else None,
        }

    return frecuencias_por_canal, espectros, resultados


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "cortocircuito_emg.parquet"
    # Por defecto compara contra prueba7Jaime (captura EMG real de referencia),
    # sin que haga falta escribirla cada vez. Se puede pasar otra como segundo
    # argumento, o "" para no comparar con ninguna.
    ruta_senal_emg = sys.argv[2] if len(sys.argv) > 2 else "prueba7Jaime_emg.parquet"
    if ruta_senal_emg == "" or not os.path.exists(ruta_senal_emg):
        if ruta_senal_emg:
            print(f"Aviso: no se encontro '{ruta_senal_emg}', no se compara con señal EMG real.\n")
        ruta_senal_emg = None
    tabla_emg = pd.read_parquet(ruta)

    duracion_s = len(tabla_emg) / FRECUENCIA_MUESTREO
    print(f"Archivo: {ruta}")
    print(f"Fs: {FRECUENCIA_MUESTREO} Hz | VREF: {VREF} V | Gain: {GANANCIA} | LSB: {LSB_UV*1000:.2f} nV/cuenta")
    print(f"Duracion: {duracion_s:.1f} s | Banda IRN: {BANDA_IRN_HZ} Hz (igual que el paper Myolink)")
    print()

    frecuencias_por_canal, espectros, irn = calcular_irn(tabla_emg)

    for canal, valores in irn.items():
        if valores["irn_rms_uv"] != valores["irn_rms_uv"]:  # NaN: ni la grabacion completa ni ninguna ventana sirvieron
            print(f"{canal}: SATURADO ({valores['saturado_pct']:.1f}% de la grabacion) -- sin ningun tramo limpio de al menos {DURACION_MINIMA_VENTANA_S:.0f}s, resultado descartado")
        elif valores["ventana_inicio_s"] is not None:
            print(f"{canal}: IRN = {valores['irn_rms_uv']:.3f} uV RMS "
                  f"(calculado solo en el tramo limpio {valores['ventana_inicio_s']:.2f}-{valores['ventana_fin_s']:.2f}s; "
                  f"el resto de la grabacion estaba saturado el {valores['saturado_pct']:.1f}% del tiempo)")
        else:
            print(f"{canal}: IRN = {valores['irn_rms_uv']:.3f} uV RMS (grabacion completa, sin saturacion)")

    tabla_irn = pd.DataFrame(
        [(canal, v["irn_rms_uv"], v["saturado_pct"], v["ventana_inicio_s"], v["ventana_fin_s"]) for canal, v in irn.items()],
        columns=["canal", "irn_rms_uv", "saturado_pct", "ventana_inicio_s", "ventana_fin_s"],
    )
    prefijo = ruta[:-len("_emg.parquet")] if ruta.endswith("_emg.parquet") else ruta.rsplit(".", 1)[0]
    tabla_irn.to_parquet(f"{prefijo}_irn.parquet")
    print(f"\nGuardado en {prefijo}_irn.parquet")

    tabla_valida = tabla_irn[tabla_irn["irn_rms_uv"].notna()]
    if tabla_valida.empty:
        print("\nNingun canal tiene datos utilizables: todos saturados sin ningun tramo limpio. Repite la grabacion.")
    else:
        media_rms = tabla_valida["irn_rms_uv"].mean()
        print(f"\nMedia entre canales validos: {media_rms:.3f} uV RMS (Myolink: {MYOLINK_IRN_RMS_UV} uV RMS)")

    # Comparacion con una señal EMG real (lo que pide el tutor): la señal
    # tiene que ser sustancialmente mayor que el ruido medido arriba. Se
    # calcula el mismo indicador (RMS en la banda 23-524 Hz, sin filtrar)
    # sobre la captura EMG que se pase como segundo argumento, para que la
    # comparacion sea justa (mismo calculo para los dos numeros).
    tabla_comparacion = None
    if ruta_senal_emg is not None:
        print(f"\nComparando con señal EMG real: {ruta_senal_emg}")
        tabla_señal = pd.read_parquet(ruta_senal_emg)
        _, _, señal_resultado = calcular_irn(tabla_señal)

        filas_comparacion = []
        for canal, v_ruido in irn.items():
            if canal not in señal_resultado or v_ruido["irn_rms_uv"] != v_ruido["irn_rms_uv"]:
                continue
            v_señal = señal_resultado[canal]
            if v_señal["irn_rms_uv"] != v_señal["irn_rms_uv"]:
                continue  # la captura EMG tambien puede tener algun canal saturado
            relacion = v_señal["irn_rms_uv"] / v_ruido["irn_rms_uv"]
            relacion_db = 20 * np.log10(relacion)
            filas_comparacion.append((canal, v_ruido["irn_rms_uv"], v_señal["irn_rms_uv"], relacion, relacion_db))
            print(f"  {canal}: ruido = {v_ruido['irn_rms_uv']:.1f} uV RMS | señal = {v_señal['irn_rms_uv']:.1f} uV RMS "
                  f"| señal/ruido = {relacion:.1f}x ({relacion_db:.1f} dB)")

        if filas_comparacion:
            tabla_comparacion = pd.DataFrame(
                filas_comparacion, columns=["canal", "ruido_uv_rms", "señal_uv_rms", "relacion", "relacion_db"],
            )
            nombre_comparacion = f"{prefijo}_irn_vs_senal.parquet"
            tabla_comparacion.to_parquet(nombre_comparacion)
            print(f"Guardado en {nombre_comparacion}")

            # Grafica: ruido vs señal, una barra de cada al lado, por canal.
            # Escala logaritmica porque la señal es decenas de veces mayor
            # que el ruido, en lineal las barras de ruido casi no se verian.
            fig_comparacion = go.Figure()
            fig_comparacion.add_trace(go.Bar(x=tabla_comparacion["canal"], y=tabla_comparacion["ruido_uv_rms"], name="Ruido (IRN)"))
            fig_comparacion.add_trace(go.Bar(x=tabla_comparacion["canal"], y=tabla_comparacion["señal_uv_rms"], name="Señal EMG real"))
            for _, fila in tabla_comparacion.iterrows():
                fig_comparacion.add_annotation(
                    x=fila["canal"], y=fila["señal_uv_rms"], text=f"{fila['relacion']:.0f}x",
                    showarrow=False, yshift=15, font=dict(size=11),
                )
            # Rango explicito por el mismo motivo que en fig_espectro: sin
            # el, Plotly puede desbocar el autorango del eje log (aunque
            # los datos sean correctos).
            fig_comparacion.update_yaxes(type="log", dtick=1, title_text="uV RMS (banda 23-524 Hz)", range=[0, 3])
            fig_comparacion.update_layout(
                title=f"Ruido vs señal EMG real, por canal - {ruta_senal_emg}",
                xaxis_title="canal",
                barmode="group",
            )
            nombre_html_comparacion = f"{prefijo}_irn_vs_senal.html"
            fig_comparacion.write_html(nombre_html_comparacion)
            print(f"Grafica de comparacion guardada en {nombre_html_comparacion}")
        else:
            print("  Ningun canal tiene a la vez ruido valido y señal valida para comparar.")

    # Grafica 1: barras de IRN integrado por canal (resumen numerico)
    fig_barras = go.Figure()
    fig_barras.add_trace(go.Bar(x=tabla_valida["canal"], y=tabla_valida["irn_rms_uv"], name="IRN (uV RMS)"))
    fig_barras.add_hline(
        y=MYOLINK_IRN_RMS_UV, line_dash="dot", line_color="green",
        annotation_text=f"Myolink ({MYOLINK_IRN_RMS_UV} uV RMS)",
    )
    fig_barras.update_layout(
        title=f"IRN por canal - {ruta}",
        xaxis_title="canal",
        yaxis_title="IRN (uV RMS)",
    )
    # Escala logaritmica: sin esto, la linea de Myolink (0,384 uV) es
    # invisible al lado de nuestros valores (decenas de uV), la diferencia
    # es de casi 3 ordenes de magnitud.
    fig_barras.update_yaxes(type="log", dtick=1, range=[-1, 2])
    nombre_html_barras = f"{prefijo}_irn.html"
    fig_barras.write_html(nombre_html_barras)
    print(f"Grafica de barras guardada en {nombre_html_barras}")

    # Grafica 2: espectro de ruido, igual que la Fig. 4(c) del paper: UNA linea
    # por sistema (el paper tampoco dibuja 32 lineas sueltas para Myolink, usa
    # una representativa), no una linea por canal. Se calcula la mediana entre
    # los canales validos (con IRN, no saturados del todo) interpolando cada
    # uno a una rejilla de frecuencia comun, ya que cada canal pudo usar una
    # ventana de tiempo distinta y por tanto tener su propia resolucion.
    canales_validos = [c for c, v in irn.items() if v["irn_rms_uv"] == v["irn_rms_uv"]]
    fig_espectro = go.Figure()
    if canales_validos:
        f_comun = np.linspace(1, FRECUENCIA_MUESTREO / 2, 500)
        espectros_interpolados = [
            np.interp(f_comun, frecuencias_por_canal[c], espectros[c]) for c in canales_validos
        ]
        mediana_sistema = np.median(espectros_interpolados, axis=0)
        mediana_valor = float(np.median(mediana_sistema))

        fig_espectro.add_trace(go.Scatter(x=f_comun, y=mediana_sistema, mode="lines", name="Sistema propio"))
        fig_espectro.add_hline(
            y=mediana_valor, line_dash="dash",
            annotation_text=f"Sistema propio: {mediana_valor:.0f} nV/sqrt(Hz) mediana",
        )
    else:
        print("\nAviso: ningun canal valido, no se puede calcular la linea del sistema propio en el espectro.")

    # Como traza (no add_hline) para que aparezca en la leyenda, no solo
    # como anotacion sobre la grafica.
    fig_espectro.add_trace(go.Scatter(
        x=[1, 1000], y=[MYOLINK_ASD_MEDIANA_NV, MYOLINK_ASD_MEDIANA_NV], mode="lines",
        line=dict(dash="dash", color="red"),
        name=f"Myolink (paper): {MYOLINK_ASD_MEDIANA_NV:.0f} nV/sqrt(Hz) mediana",
    ))
    # exponentformat="power": mismo estilo de notacion que el paper (10^0,
    # 10^1, 10^2...), en vez de la mezcla de sufijos (k, M, B, T) que pone
    # Plotly por defecto cuando el rango de valores es muy grande.
    fig_espectro.update_xaxes(type="log", dtick=1, exponentformat="power", title_text="Frecuencia (Hz)", range=[0, 3])  # 1 a 1000 Hz, igual que Fig. 4c
    # Rango explicito en el eje Y: sin esto, Plotly a veces calcula mal el
    # autorango de un eje log combinado con add_hline (se ha visto expandirse
    # hasta 10^60 sin motivo), aunque los datos en si sean correctos.
    fig_espectro.update_yaxes(type="log", dtick=1, exponentformat="power", title_text="Densidad de ruido (nV/sqrt(Hz))", range=[0, 8])
    fig_espectro.update_layout(title=f"Espectro de ruido en cortocircuito, estilo Myolink Fig. 4(c) - {ruta}")
    nombre_html_espectro = f"{prefijo}_irn_espectro.html"
    fig_espectro.write_html(nombre_html_espectro)
    print(f"Espectro guardado en {nombre_html_espectro}")

    # Version estatica (PDF + PNG) del mismo espectro, para meter en la
    # memoria: pdflatex admite PDF vectorial directamente (mejor calidad
    # que un PNG para lineas y texto), el PNG es solo para verlo rapido
    # sin abrir el PDF.
    if canales_validos:
        fig_mpl, ax = plt.subplots(figsize=(7, 5))
        for c in canales_validos:
            ax.plot(frecuencias_por_canal[c], espectros[c], alpha=0.5, lw=0.8, label=c)
        ax.plot(f_comun, mediana_sistema, color="black", lw=2, label="Sistema propio (mediana)")
        ax.axhline(MYOLINK_ASD_MEDIANA_NV, color="red", ls="--", label=f"Myolink ({MYOLINK_ASD_MEDIANA_NV:.0f} nV/√Hz)")
        ax.axvspan(BANDA_IRN_HZ[0], BANDA_IRN_HZ[1], color="gray", alpha=0.1)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(1, 1000)
        ax.set_ylim(1, 1e8)
        ax.set_xlabel("Frecuencia (Hz)")
        ax.set_ylabel("ASD (nV/√Hz)")
        ax.set_title("Espectro de ruido en cortocircuito, referido al electrodo")
        ax.legend(fontsize=7, ncol=2)
        fig_mpl.tight_layout()

        nombre_pdf_espectro = f"{prefijo}_irn_espectro.pdf"
        nombre_png_espectro = f"{prefijo}_irn_espectro.png"
        fig_mpl.savefig(nombre_pdf_espectro)
        fig_mpl.savefig(nombre_png_espectro, dpi=200)
        plt.close(fig_mpl)
        print(f"Espectro estatico guardado en {nombre_pdf_espectro} y {nombre_png_espectro}")

    # Se abre al final (y solo esta) la grafica de comparacion ruido vs
    # señal, que es la que pidio el tutor: si se llaman varias fig.show()
    # seguidas en el mismo script, solo la ultima se abre de forma fiable.
    if tabla_comparacion is not None:
        fig_comparacion.show()
    else:
        fig_barras.show()

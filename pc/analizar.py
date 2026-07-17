import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

tabla_emg = pd.read_parquet("captura_emg.parquet")
print(tabla_emg)

FRECUENCIA_MUESTREO = 100
tiempo = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

for columna in tabla_emg.columns:
    plt.plot(tiempo, tabla_emg[columna], label=columna)


plt.xlabel("tiempo (s)")
plt.ylabel("valor EMG")
plt.title("Señal capturada - 8 canales")

plt.show()
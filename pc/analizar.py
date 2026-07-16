import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

tabla_emg = pd.read_parquet("captura_emg.parquet")
print(tabla_emg)

FRECUENCIA_MUESTREO = 100
tiempo = np.arange(len(tabla_emg)) / FRECUENCIA_MUESTREO

plt.plot(tiempo, tabla_emg["emg"])
plt.xlabel("tiempo (s)")
plt.ylabel("valor EMG")
plt.title("Señal capturada")
plt.show()
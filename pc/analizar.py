import pandas as pd
import matplotlib.pyplot as plt

tabla_emg = pd.read_parquet("captura_emg.parquet")
print(tabla_emg)

plt.plot(tabla_emg["emg"])
plt.xlabel("muestra")
plt.ylabel("valor EMG")
plt.title("Señal capturada")
plt.show()
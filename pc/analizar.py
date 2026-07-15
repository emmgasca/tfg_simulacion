import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_parquet("captura_emg.parquet")
print(df)

plt.plot(df["emg"])
plt.xlabel("muestra")
plt.ylabel("valor EMG")
plt.title("Señal capturada")
plt.show()
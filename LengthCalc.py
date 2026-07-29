import pandas as pd

df = pd.read_parquet(r'C:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\tibialis_2contracciones_500Hz.parquet')

print(df.shape[0]/60)
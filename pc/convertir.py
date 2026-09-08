import pandas as pd
import os

for f in os.listdir(r"C:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\pc"):
    if f.endswith(".parquet"):
        data = pd.read_parquet(os.path.join(r"C:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\pc", f))
        data.to_csv(os.path.join(r"C:\Users\emmag\Documents\PlatformIO\Projects\TFG_simulacion\pc", f.replace(".parquet", ".csv")), index=False)

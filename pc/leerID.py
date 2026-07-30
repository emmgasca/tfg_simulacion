import pandas as pd

df = pd.read_parquet("prueba_emg.parquet")

print(df.head())
print(df.columns)
print(len(df))

print(df.describe())

# --- Analisis de huecos en la secuencia de MUESTRAS ---
# paquete_id es un numero de secuencia POR MUESTRA (formato ParkEMG "PB" v2),
# no por paquete: cada paquete trae 10 muestras con 10 paquete_id consecutivos.
# Por eso aqui ya no hace falta multiplicar nada por 10.
ids_unicos = df["paquete_id"].drop_duplicates().reset_index(drop=True)
saltos = ids_unicos.diff()

huecos = ids_unicos[saltos > 1]
print("Huecos encontrados:", len(huecos))
print(huecos)

tamanos_hueco = (saltos[saltos > 1] - 1)
print("\nTamano de cada hueco (cuantas muestras se perdieron de una vez):")
print(tamanos_hueco.value_counts())

distancia_entre_huecos = huecos.diff()
print("\nDistancia entre huecos consecutivos (cada cuantas muestras se repite):")
print(distancia_entre_huecos.value_counts())

# --- Resumen ---
muestras_esperadas = ids_unicos.max() - ids_unicos.min() + 1
muestras_recibidas = len(ids_unicos)
muestras_perdidas = muestras_esperadas - muestras_recibidas
print(f"\nMuestras esperadas: {muestras_esperadas}")
print(f"Muestras recibidas: {muestras_recibidas}")
print(f"Muestras perdidas: {muestras_perdidas} ({100 * muestras_perdidas / muestras_esperadas:.1f}%)")
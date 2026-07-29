import pandas as pd

df = pd.read_parquet("prueba_emg.parquet")

print(df.head())
print(df.columns)
print(len(df))

print(df.describe())

# --- Analisis de huecos en la secuencia de paquetes ---
ids_unicos = df["paquete_id"].drop_duplicates().reset_index(drop=True)
saltos = ids_unicos.diff()

huecos = ids_unicos[saltos > 1]
print("Huecos encontrados:", len(huecos))
print(huecos)

tamanos_hueco = (saltos[saltos > 1] - 1)
print("\nTamano de cada hueco (cuantos paquetes se perdieron de una vez):")
print(tamanos_hueco.value_counts())

distancia_entre_huecos = huecos.diff()
print("\nDistancia entre huecos consecutivos (cada cuantos paquetes se repite):")
print(distancia_entre_huecos.value_counts())

# --- Resumen ---
total_posibles = ids_unicos.max() - ids_unicos.min() + 1
total_recibidos = len(ids_unicos)
total_perdidos = total_posibles - total_recibidos
print(f"\nPaquetes esperados: {total_posibles}")
print(f"Paquetes recibidos: {total_recibidos}")
print(f"Paquetes perdidos: {total_perdidos} ({100 * total_perdidos / total_posibles:.1f}%)")
print(f"\nMuestras esperadas: {total_posibles * 10}")
print(f"Muestras recibidas: {len(df)}")
print(f"Muestras perdidas: {total_perdidos * 10}")
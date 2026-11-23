import pandas as pd
import sqlite3
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

print("--- 1. EXTRACCIÓN Y CARGA ---")
conn = sqlite3.connect('calidad_aire.db')
query = "SELECT * FROM lecturas_aire ORDER BY id ASC"
df = pd.read_sql_query(query, conn)
conn.close()

df['fecha_registro'] = pd.to_datetime(df['fecha_registro'])
df = df.dropna()
print(f"Total de registros cargados: {len(df)}")
print(df.head())

print("\n--- 2. ESTADÍSTICA DESCRIPTIVA ---")
columnas_analisis = ['gas', 'latencia', 'temperatura', 'humedad']

for col in columnas_analisis:
    media = df[col].mean()
    mediana = df[col].median()
    moda = df[col].mode()[0]
    desv = df[col].std()
    var = df[col].var()
    print(f"[{col.upper()}] Media: {media:.2f} | Mediana: {mediana:.2f} | Moda: {moda:.2f} | Std: {desv:.2f} | Var: {var:.2f}")

Q1 = df['latencia'].quantile(0.25)
Q3 = df['latencia'].quantile(0.75)
IQR = Q3 - Q1
limite_superior = Q3 + 1.5 * IQR
outliers = df[df['latencia'] > limite_superior]
print(f"\nOutliers detectados en Latencia (> {limite_superior:.2f} ms): {len(outliers)} paquetes.")

print("\n--- 3. DIAGNÓSTICO DE RED ---")
df['delta_t_ms'] = df['fecha_registro'].diff().dt.total_seconds() * 1000
media_delta = df['delta_t_ms'].mean()
print(f"Intervalo efectivo de llegada promedio (Delta T): {media_delta:.2f} ms")

if len(df) > 0:
    seq_min = df['sequence_id'].min()
    seq_max = df['sequence_id'].max()
    mensajes_esperados = seq_max - seq_min + 1
    mensajes_recibidos = len(df)
    p_perdida = (1 - (mensajes_recibidos / mensajes_esperados)) * 100
    print(f"Pérdida de Paquetes Formal: {p_perdida:.2f}% (Recibidos: {mensajes_recibidos} / Esperados: {mensajes_esperados})")

sns.set_theme(style="darkgrid")
fig, axs = plt.subplots(2, 2, figsize=(14, 10))

axs[0, 0].plot(df['fecha_registro'], df['gas'], color='teal', linewidth=1.5)
axs[0, 0].set_title('Evolución Temporal del Gas (MQ-135)')
axs[0, 0].set_xlabel('Tiempo')
axs[0, 0].set_ylabel('Valor ADC crudo')
axs[0, 0].tick_params(axis='x', rotation=45)

sns.boxplot(y=df['latencia'], ax=axs[0, 1], color='salmon')
axs[0, 1].set_title('Diagrama de Caja de Latencia de Red (ms)')

sns.histplot(df['gas'], bins=30, kde=True, ax=axs[1, 0], color='purple')
axs[1, 0].set_title('Distribución de Frecuencia Analógica (Gas)')

corr = df[['gas', 'temperatura', 'humedad', 'latencia', 'delta_t_ms']].corr()
sns.heatmap(corr, annot=True, cmap='coolwarm', ax=axs[1, 1], vmin=-1, vmax=1)
axs[1, 1].set_title('Heatmap de Correlación entre Variables')

plt.tight_layout()
plt.show()
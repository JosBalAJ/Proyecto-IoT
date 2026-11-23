import pandas as pd
import sqlite3
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import joblib

print("Extrayendo datos históricos de SQLite...")
conn = sqlite3.connect('calidad_aire.db')
df = pd.read_sql_query("SELECT * FROM lecturas_aire ORDER BY id ASC", conn)
conn.close()

df['fecha_registro'] = pd.to_datetime(df['fecha_registro'])
df['delta_t_ms'] = df['fecha_registro'].diff().dt.total_seconds() * 1000
df = df.dropna()

def etiquetar_estado(row):
    if row['gas'] >= 1000 or row['temperatura'] >= 30.0:
        return 'Riesgo Respiratorio'
    elif row['gas'] >= 700 or row['temperatura'] >= 29.0:
        return 'Requiere Ventilación'
    return 'Aire Limpio/Seguro'

df['estado_sistema'] = df.apply(etiquetar_estado, axis=1)

X = df[['gas', 'temperatura', 'humedad', 'latencia']]
y = df['estado_sistema']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

print("Entrenando el modelo Random Forest...")
rf_model = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    criterion='gini'
)
rf_model.fit(X_train, y_train)

y_pred = rf_model.predict(X_test)
print("\n--- REPORTE DE CLASIFICACIÓN ---")
print(classification_report(y_test, y_pred))

cm = confusion_matrix(y_test, y_pred, labels=['Aire Limpio/Seguro', 'Requiere Ventilación', 'Riesgo Respiratorio'])
plt.figure(figsize=(8,6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
            xticklabels=['Limpio', 'Ventilación', 'Riesgo'],
            yticklabels=['Limpio', 'Ventilación', 'Riesgo'])
plt.xlabel('Predicción del Modelo Random Forest')
plt.ylabel('Valor Real (Ground Truth)')
plt.title('Matriz de Confusión - Clasificación de Eventos IoT')
plt.tight_layout()
plt.show()

importances = rf_model.feature_importances_
df_importance = pd.DataFrame({'Característica': X.columns, 'Importancia': importances})
df_importance = df_importance.sort_values(by='Importancia', ascending=False)

plt.figure(figsize=(8,4))
sns.barplot(x='Importancia', y='Característica', data=df_importance, palette='viridis')
plt.title('Importancia de las Características (Feature Importance)')
plt.tight_layout()
plt.show()

joblib.dump(rf_model, 'modelo_rf_aire.pkl')
print("\nModelo guardado exitosamente como 'modelo_rf_aire.pkl'")
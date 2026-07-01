# 📦 Dashboard Inventario Cíclico · Cargoflex

Dashboard en tiempo real que lee directamente desde Google Sheets y muestra:
- **Cobertura del universo** — cuántos códigos han sido contados vs el total en stock
- **Exactitud por cliente** — OK / (OK + Revisar + Ajuste)
- **Cumplimiento diario** — SKUs contados / SKUs generados por día
- **Evolución diaria** — exactitud + volumen por día
- **Top SKUs problema** — códigos con más ajustes recurrentes
- **Filtros** — por bodega y cliente, todo se recalcula en tiempo real

---

## 🗂️ Estructura del repo

```
inventario_dash/
├── app.py                          ← código principal del dashboard
├── requirements.txt                ← dependencias de Python
├── .gitignore                      ← excluye credentials y datos sensibles
├── .streamlit/
│   └── secrets.toml.template       ← plantilla de configuración (no subir secrets.toml)
└── README.md
```

---

## ⚙️ Configuración local (para pruebas en tu PC)

### 1. Clonar el repo
```bash
git clone https://github.com/TU_USUARIO/inventario-ciclico.git
cd inventario-ciclico
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar credenciales locales
```bash
# Crea el archivo de secrets local (NO se sube al repo)
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```
Edita `.streamlit/secrets.toml` con:
- Los IDs de tus dos Google Sheets
- El contenido de tu `credentials.json` de Google Cloud

### 4. Correr localmente
```bash
streamlit run app.py
```
Se abre en http://localhost:8501

---

## 🚀 Despliegue en Streamlit Cloud

### Paso 1 — Subir a GitHub
```bash
git add .
git commit -m "dashboard inventario ciclico"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/inventario-ciclico.git
git push -u origin main
```

### Paso 2 — Crear la app en Streamlit Cloud
1. Ir a [share.streamlit.io](https://share.streamlit.io)
2. **New app** → conectar con GitHub → seleccionar el repo
3. Main file path: `app.py`
4. Clic en **Advanced settings** → sección **Secrets**

### Paso 3 — Configurar Secrets en Streamlit Cloud
Pegar este contenido en el campo Secrets (con tus valores reales):

```toml
[sheets]
sheet_id_historial = "1hIynrrwPXHNrvl8hAuZHaTZEtwQn1jfW8apJsUCKFRo"
sheet_id_stock_wms = "ID_DEL_SHEET_STOCK_WMS"
nombre_hoja_stock  = "Hoja 1"

[gcp_service_account]
type                        = "service_account"
project_id                  = "tu-proyecto"
private_key_id              = "..."
private_key                 = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email                = "inventario-bot@tu-proyecto.iam.gserviceaccount.com"
client_id                   = "..."
auth_uri                    = "https://accounts.google.com/o/oauth2/auth"
token_uri                   = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url        = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

### Paso 4 — Deploy
Clic en **Deploy** — en ~2 minutos el dashboard estará en:
`https://TU_USUARIO.streamlit.app`

### Actualizaciones futuras
Cada vez que hagas cambios:
```bash
git add .
git commit -m "descripcion del cambio"
git push
```
Streamlit Cloud redespliega automáticamente en ~1 minuto.

---

## 🔑 IDs de los Sheets

| Sheet | ID |
|---|---|
| HISTORIAL-INVENTARIO-CICLICO | `1hIynrrwPXHNrvl8hAuZHaTZEtwQn1jfW8apJsUCKFRo` |
| Reporte Stock WMS Diario | _(agregar aquí tu ID)_ |

---

## 📊 Fuentes de datos

| Fuente | Actualización | Uso en el dash |
|---|---|---|
| HISTORIAL-INVENTARIO-CICLICO | Al cerrar el día (Apps Script 6pm) | Exactitud, cumplimiento, top SKUs |
| Reporte Stock WMS Diario | Automático 7am | Cobertura del universo |

El dashboard se actualiza automáticamente cada **5 minutos** leyendo ambos Sheets.

---

## 🛠️ Tecnologías

- [Streamlit](https://streamlit.io) — framework del dashboard
- [gspread](https://gspread.readthedocs.io) — lectura de Google Sheets
- [Plotly](https://plotly.com/python/) — gráficos interactivos
- [Pandas](https://pandas.pydata.org) — análisis de datos

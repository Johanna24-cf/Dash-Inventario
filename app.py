"""
Dashboard Inventario Cíclico — Cargoflex
=========================================
Lee en tiempo real desde dos Google Sheets:
  - HISTORIAL-INVENTARIO-CICLICO (pestañas HIST_AAAA_MM)
  - Reporte Stock WMS Diario (Hoja 1)
  - Sheet Master (pestaña CONFIG — lista de clientes válidos)

Despliegue: Streamlit Cloud + GitHub
Credenciales: st.secrets["gcp_service_account"]
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2 import service_account
import gspread
from datetime import datetime
import re

# ─── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Inventario Cíclico · Cargoflex",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Estilos — Tema claro Cargoflex ──────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #F7F9F7; }
  [data-testid="stMain"] { background: #F7F9F7; }
  [data-testid="stSidebar"] { background: #1A4731; border-right: 1px solid #145229; }
  [data-testid="stSidebar"] * { color: #E8F5E9 !important; }
  [data-testid="stSidebar"] select { background: #145229 !important; color: #E8F5E9 !important; border: 1px solid #2E7D52 !important; }
  [data-testid="stSidebar"] hr { border-color: #2E7D52 !important; }
  [data-testid="stSidebar"] button { background: #2E7D52 !important; color: white !important; border-radius: 6px !important; }
  .metric-card {
    background: #FFFFFF; border: 1px solid #C8E6C9; border-radius: 10px;
    padding: 16px 20px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }
  .metric-label { font-size: 11px; color: #5F8B6E; margin: 0 0 6px; text-transform: uppercase; letter-spacing: .5px; font-weight: 600; }
  .metric-value { font-size: 28px; font-weight: 700; margin: 0; line-height: 1.2; }
  .metric-sub   { font-size: 11px; color: #8DAF96; margin: 4px 0 0; }
  .c-ok   { color: #2E7D32; }
  .c-warn { color: #E65100; }
  .c-err  { color: #C62828; }
  .c-neu  { color: #1A4731; }
  .alert-box { border-radius: 8px; padding: 12px 16px; display: flex; gap: 10px; margin-bottom: 10px; }
  .alert-red  { background: #FFEBEE; border-left: 3px solid #C62828; }
  .alert-warn { background: #FFF3E0; border-left: 3px solid #E65100; }
  .alert-title { font-size: 13px; font-weight: 600; margin: 0 0 3px; color: #1A1A1A; }
  .alert-body  { font-size: 12px; color: #555; margin: 0; }
  .section-title {
    font-size: 12px; font-weight: 700; color: #2E7D32;
    text-transform: uppercase; letter-spacing: .5px; margin: 20px 0 10px;
    border-bottom: 2px solid #C8E6C9; padding-bottom: 6px;
  }
  [data-testid="stTabs"] [role="tab"] { color: #5F8B6E !important; font-weight: 500; }
  [data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #1A4731 !important; border-bottom-color: #2E7D32 !important; }
  h1, h2, h3, p, span, div { color: #1A1A1A; }
  [data-testid="stCaption"] { color: #5F8B6E !important; }
  div[data-testid="stSelectbox"] label { font-size: 13px !important; color: #2E7D32 !important; font-weight: 500 !important; }
  div[data-testid="stSelectbox"] div[data-baseweb="select"] { border-color: #A5D6A7 !important; }
  [data-testid="stDataFrame"] { border: 1px solid #C8E6C9; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

UBICACIONES_EXCLUIR = ['C1-DSP-1', 'C1-REC-1']

PLOT_LIGHT = dict(plot_bgcolor="#FFFFFF", paper_bgcolor="#F7F9F7")
PLOT_FONT  = dict(color="#1A1A1A", size=11)
GRID_COLOR = "#E8F5E9"
GREEN_DARK  = "#1A4731"
GREEN_MID   = "#2E7D32"
GREEN_LIGHT = "#81C784"
ORANGE      = "#E65100"
RED         = "#C62828"

# ─── Conexión Google Sheets ───────────────────────────────────────────────────
@st.cache_resource(ttl=300)
def get_client():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner="Cargando clientes válidos desde CONFIG...")
def cargar_clientes_validos():
    """Lee la pestaña CONFIG del Sheet Master y devuelve set de familias válidas."""
    client = get_client()
    sh = client.open_by_key(st.secrets["sheets"]["sheet_id_master"])
    ws = sh.worksheet("CONFIG")
    datos = ws.get_all_values()
    clientes = []
    leyendo = False
    for fila in datos:
        col0 = str(fila[0]).strip() if fila else ""
        col1 = str(fila[1]).strip() if len(fila) > 1 else ""
        if col0 == "CLIENTES ABC":
            leyendo = True
            continue
        if col0 == "Familia":
            continue
        if leyendo and not col0:
            break
        if leyendo and col0 and col1:
            clientes.append(col0)
    return set(clientes)


@st.cache_data(ttl=300, show_spinner="Actualizando historial...")
def cargar_historial(clientes_validos):
    """Lee todas las pestañas HIST_AAAA_MM y filtra solo clientes válidos."""
    client = get_client()
    sh = client.open_by_key(st.secrets["sheets"]["sheet_id_historial"])
    frames = []
    for ws in sh.worksheets():
        if re.match(r"HIST_\d{4}_\d{2}", ws.title):
            data = ws.get_all_records()
            if data:
                df = pd.DataFrame(data)
                df["_sheet"] = ws.title
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.strip() for c in df.columns]

    # Filtrar solo clientes válidos del CONFIG
    if "Cliente" in df.columns and clientes_validos:
        df = df[df["Cliente"].isin(clientes_validos)]

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
    if "Código SKU" in df.columns:
        df["Código SKU"] = df["Código SKU"].astype(str).str.lstrip("'").str.strip()
    if "Stock WMS" in df.columns:
        df["Stock WMS"] = pd.to_numeric(df["Stock WMS"], errors="coerce").fillna(0)
    if "Contado" in df.columns:
        df["Contado"] = pd.to_numeric(df["Contado"], errors="coerce")

    return df


@st.cache_data(ttl=300, show_spinner="Actualizando stock WMS...")
def cargar_stock_wms(clientes_validos):
    """Lee el reporte de stock diario y filtra solo clientes válidos."""
    client = get_client()
    sh = client.open_by_key(st.secrets["sheets"]["sheet_id_stock_wms"])
    ws = sh.worksheet(st.secrets["sheets"].get("nombre_hoja_stock", "Hoja 1"))
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df.columns = [c.strip() for c in df.columns]

    # Filtrar solo clientes válidos del CONFIG
    if "Familia" in df.columns and clientes_validos:
        df = df[df["Familia"].isin(clientes_validos)]

    if "Ubicación" in df.columns:
        df = df[~df["Ubicación"].isin(UBICACIONES_EXCLUIR)]

    col_stock = next((c for c in df.columns if "Stock" in c and "Físico" in c), None)
    if col_stock:
        df[col_stock] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0)
        df = df[df[col_stock] > 0]
        df = df.rename(columns={col_stock: "Stock Físico"})

    return df


# ─── Helpers ──────────────────────────────────────────────────────────────────
def calcular_exactitud_ubicacion(df):
    """Exactitud por ubicación: OK / (OK + Revisar + Ajuste)."""
    contados = df[df["Estado"] != "⏳ Pendiente"]
    ok = (contados["Estado"] == "✅ OK").sum()
    total = len(contados)
    return (ok / total * 100) if total > 0 else 0, ok, total


def calcular_exactitud_sku(df):
    """
    Exactitud por SKU: suma contado total del código vs suma stock WMS total.
    Si contado_total == stock_wms_total → SKU OK (aunque ubicaciones no coincidan).
    Solo considera SKUs que tengan al menos 1 fila contada (no toda pendiente).
    """
    if "Código SKU" not in df.columns or "Stock WMS" not in df.columns or "Contado" not in df.columns:
        return 0, 0, 0

    # Solo filas con conteo registrado
    df_cont = df[df["Contado"].notna()].copy()
    if df_cont.empty:
        return 0, 0, 0

    # Agrupar por código SKU
    por_sku = df_cont.groupby("Código SKU").agg(
        total_contado=("Contado", "sum"),
        total_wms=("Stock WMS", "sum"),
    ).reset_index()

    total_skus  = len(por_sku)
    skus_ok     = (por_sku["total_contado"] == por_sku["total_wms"]).sum()
    exactitud   = (skus_ok / total_skus * 100) if total_skus > 0 else 0
    return exactitud, skus_ok, total_skus


def filtrar_df(df, bodega_map, bodega, cliente):
    if "Cliente" not in df.columns:
        return df
    if bodega != "Todas":
        clientes_bodega = [c for c, b in bodega_map.items() if b == bodega]
        df = df[df["Cliente"].isin(clientes_bodega)]
    if cliente != "Todos":
        df = df[df["Cliente"] == cliente]
    return df


def card(label, value, sub="", color="c-neu"):
    st.markdown(f"""
    <div class="metric-card">
      <p class="metric-label">{label}</p>
      <p class="metric-value {color}">{value}</p>
      <p class="metric-sub">{sub}</p>
    </div>""", unsafe_allow_html=True)


def alert(title, body, tipo="red"):
    cls = "alert-red" if tipo == "red" else "alert-warn"
    icon = "🔴" if tipo == "red" else "🟡"
    st.markdown(f"""
    <div class="alert-box {cls}">
      <span>{icon}</span>
      <div>
        <p class="alert-title">{title}</p>
        <p class="alert-body">{body}</p>
      </div>
    </div>""", unsafe_allow_html=True)


# ─── LAYOUT ───────────────────────────────────────────────────────────────────
st.markdown('<h2 style="color:#1A4731;font-weight:700;">📦 Inventario Cíclico · Cargoflex</h2>',
            unsafe_allow_html=True)
st.caption(f"Actualizado cada 5 min · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# Cargar clientes válidos primero
try:
    clientes_validos = cargar_clientes_validos()
except Exception as e:
    st.error(f"Error leyendo CONFIG del Sheet Master: {e}")
    st.stop()

# Cargar datos filtrados por clientes válidos
with st.spinner("Cargando datos..."):
    df_hist = cargar_historial(clientes_validos)
    df_wms  = cargar_stock_wms(clientes_validos)

if df_hist.empty:
    st.error("No se encontraron datos. Verifica los IDs en st.secrets y que la cuenta de servicio tenga acceso.")
    st.stop()

# Mapa bodega por cliente (desde historial, solo clientes válidos)
CLIENTES_BODEGA = {}
if "Cliente" in df_wms.columns and "Bodega" in df_wms.columns:
    CLIENTES_BODEGA = df_wms.drop_duplicates("Familia")[["Familia","Bodega"]].set_index("Familia")["Bodega"].to_dict() if "Familia" in df_wms.columns else {}

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Filtros")
    st.divider()

    # Filtro mes
    if "Fecha" in df_hist.columns:
        meses_disp = sorted(df_hist["Fecha"].dropna().dt.to_period("M").unique(), reverse=True)
        meses_str  = ["Todos"] + [str(m) for m in meses_disp]
        mes_sel    = st.selectbox("Mes", meses_str)
    else:
        mes_sel = "Todos"

    # Filtro bodega
    bodegas_disp = ["Todas"]
    if df_wms is not None and "Bodega" in df_wms.columns:
        bodegas_disp += sorted(df_wms["Bodega"].dropna().unique().tolist())
    bodega_sel = st.selectbox("Bodega", bodegas_disp)

    # Filtro cliente (depende de bodega)
    df_temp = df_hist.copy()
    if bodega_sel != "Todas" and df_wms is not None and "Familia" in df_wms.columns and "Bodega" in df_wms.columns:
        clis_bodega = df_wms[df_wms["Bodega"] == bodega_sel]["Familia"].unique().tolist()
        df_temp = df_temp[df_temp["Cliente"].isin(clis_bodega)]
    clientes_disp = ["Todos"] + sorted(df_temp["Cliente"].dropna().unique().tolist()) if "Cliente" in df_temp.columns else ["Todos"]
    cliente_sel = st.selectbox("Cliente", clientes_disp)

    st.divider()
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Datos actualizados automáticamente cada 5 minutos.")

# ─── APLICAR FILTROS ──────────────────────────────────────────────────────────
df = df_hist.copy()
if mes_sel != "Todos" and "Fecha" in df.columns:
    df = df[df["Fecha"].dt.to_period("M").astype(str) == mes_sel]

# Filtro bodega en historial
if bodega_sel != "Todas" and df_wms is not None and "Familia" in df_wms.columns and "Bodega" in df_wms.columns:
    clis_bod = df_wms[df_wms["Bodega"] == bodega_sel]["Familia"].unique().tolist()
    df = df[df["Cliente"].isin(clis_bod)]

if cliente_sel != "Todos":
    df = df[df["Cliente"] == cliente_sel]

# Filtro WMS
wms_f = df_wms.copy() if df_wms is not None else pd.DataFrame()
if bodega_sel != "Todas" and "Bodega" in wms_f.columns:
    wms_f = wms_f[wms_f["Bodega"] == bodega_sel]
if cliente_sel != "Todos" and "Familia" in wms_f.columns:
    wms_f = wms_f[wms_f["Familia"] == cliente_sel]

# ─── KPIs ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="section-title">Resumen del período</p>', unsafe_allow_html=True)

total_filas = len(df)

# Exactitud por ubicación
exact_ubic, ok_ubic, cont_ubic = calcular_exactitud_ubicacion(df)

# Exactitud por SKU
exact_sku, ok_sku, total_skus_cont = calcular_exactitud_sku(df)

pendientes = (df["Estado"] == "⏳ Pendiente").sum() if "Estado" in df.columns else 0
ajustes    = (df["Estado"] == "❌ Ajuste").sum() if "Estado" in df.columns else 0
cum        = (cont_ubic / total_filas * 100) if total_filas > 0 else 0

# Cobertura universo
col_cod_wms = next((c for c in wms_f.columns if "Código" in c), None)
if col_cod_wms and not wms_f.empty and "Código SKU" in df.columns:
    universo_total = wms_f[col_cod_wms].astype(str).nunique()
    cod_contados   = df[df["Estado"] != "⏳ Pendiente"]["Código SKU"].astype(str).nunique() if "Estado" in df.columns else 0
    pct_cob        = min((cod_contados / universo_total * 100) if universo_total > 0 else 0, 100)
else:
    universo_total = 0; cod_contados = 0; pct_cob = 0

cols = st.columns(6)
with cols[0]:
    color = "c-err" if pct_cob < 20 else ("c-warn" if pct_cob < 60 else "c-ok")
    card("Cobertura universo", f"{pct_cob:.1f}%", f"{cod_contados:,} de {universo_total:,} códigos", color)
with cols[1]:
    color = "c-err" if exact_ubic < 60 else ("c-warn" if exact_ubic < 80 else "c-ok")
    card("Exactitud ubicación", f"{exact_ubic:.1f}%", f"{ok_ubic:,} OK de {cont_ubic:,} contados", color)
with cols[2]:
    color = "c-err" if exact_sku < 60 else ("c-warn" if exact_sku < 80 else "c-ok")
    card("Exactitud por SKU", f"{exact_sku:.1f}%", f"{ok_sku:,} OK de {total_skus_cont:,} códigos", color)
with cols[3]:
    color = "c-err" if cum < 50 else ("c-warn" if cum < 80 else "c-ok")
    card("Cumplimiento", f"{cum:.1f}%", f"{cont_ubic:,} de {total_filas:,} filas", color)
with cols[4]:
    color = "c-err" if ajustes > 50 else ("c-warn" if ajustes > 10 else "c-ok")
    card("Ajustes", f"{ajustes:,}", f"{(ajustes/cont_ubic*100):.1f}% de contados" if cont_ubic else "—", color)
with cols[5]:
    pct_pend = (pendientes / total_filas * 100) if total_filas > 0 else 0
    color = "c-err" if pct_pend > 40 else ("c-warn" if pct_pend > 20 else "c-ok")
    card("Pendientes", f"{pendientes:,}", f"{pct_pend:.1f}% del total generado", color)

st.divider()

# ─── ALERTAS ──────────────────────────────────────────────────────────────────
if "Cliente" in df.columns and "Estado" in df.columns and len(df) > 0:
    res_cli = df.groupby("Cliente").apply(
        lambda x: pd.Series({
            "ok": (x["Estado"] == "✅ OK").sum(),
            "contados": (x["Estado"] != "⏳ Pendiente").sum(),
            "pendientes": (x["Estado"] == "⏳ Pendiente").sum(),
            "total": len(x),
        })
    ).reset_index()
    res_cli["exactitud"] = res_cli.apply(
        lambda r: r["ok"] / r["contados"] * 100 if r["contados"] > 0 else None, axis=1
    )
    criticos   = res_cli[res_cli["exactitud"] < 20].sort_values("exactitud")
    sin_conteo = res_cli[res_cli["contados"] == 0]

    for _, row in criticos.iterrows():
        alert(
            f"{row['Cliente']}: exactitud crítica de {row['exactitud']:.0f}%",
            f"{row['ok']} OK de {row['contados']} contados. Revisar si hay error de ubicación en WMS.",
            "red"
        )
    if not sin_conteo.empty:
        nombres = ", ".join(sin_conteo["Cliente"].tolist()[:5])
        alert(
            f"{len(sin_conteo)} cliente(s) sin ningún conteo en el período",
            f"{nombres}{'...' if len(sin_conteo) > 5 else ''}. Verificar rotación en ROTACION sheet.",
            "warn"
        )
    if "Fecha" in df.columns:
        dias_0 = df.groupby(df["Fecha"].dt.date).apply(
            lambda x: (x["Estado"] != "⏳ Pendiente").sum() == 0
        )
        n_dias_0 = dias_0.sum()
        if n_dias_0 > 0:
            fechas_0 = ", ".join([d.strftime("%d/%m") for d in dias_0[dias_0].index])
            alert(
                f"{n_dias_0} día(s) con 0% de cumplimiento",
                f"Fechas: {fechas_0}. La lista se generó pero nadie registró conteos.",
                "red"
            )

st.divider()

# ─── TABS ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Cobertura del universo",
    "📍 Exactitud por ubicación",
    "🎯 Exactitud por SKU",
    "📈 Cumplimiento diario",
    "📅 Exactitud diaria",
    "⚠️ Top SKUs problema",
])

# ── TAB 1: COBERTURA DEL UNIVERSO ─────────────────────────────────────────────
with tab1:
    if wms_f.empty or col_cod_wms is None:
        st.info("No hay datos de stock WMS disponibles.")
    else:
        col_fam = "Familia" if "Familia" in wms_f.columns else None
        if col_fam:
            universo_cli = wms_f.groupby(col_fam)[col_cod_wms].nunique().reset_index()
            universo_cli.columns = ["Cliente", "Universo"]

            hist_c = df[df["Estado"] != "⏳ Pendiente"] if "Estado" in df.columns else df
            if "Código SKU" in hist_c.columns:
                cont_cli = hist_c.groupby("Cliente")["Código SKU"].nunique().reset_index()
                cont_cli.columns = ["Cliente", "Contados"]
            else:
                cont_cli = pd.DataFrame(columns=["Cliente", "Contados"])

            cob = universo_cli.merge(cont_cli, on="Cliente", how="left").fillna(0)
            cob["Contados"] = cob["Contados"].astype(int)
            cob["% Cobertura"] = (cob["Contados"] / cob["Universo"] * 100).clip(upper=100).round(1)
            cob["Pendientes"] = cob["Universo"] - cob["Contados"]
            cob = cob.sort_values("% Cobertura", ascending=True)

            def color_cob(p):
                if p >= 50: return GREEN_MID
                if p >= 10: return ORANGE
                return RED

            fig = go.Figure()
            for _, row in cob.iterrows():
                fig.add_trace(go.Bar(
                    x=[row["% Cobertura"]],
                    y=[row["Cliente"]],
                    orientation="h",
                    marker_color=color_cob(row["% Cobertura"]),
                    text=f"{row['Contados']}/{row['Universo']}",
                    textposition="inside",
                    textfont=dict(color="white", size=10),
                    customdata=[[row["% Cobertura"]]],
                    hovertemplate=(
                        f"<b>{row['Cliente']}</b><br>"
                        f"Contados: {row['Contados']}<br>"
                        f"Universo: {row['Universo']}<br>"
                        f"Cobertura: {row['% Cobertura']}%<extra></extra>"
                    ),
                    showlegend=False,
                ))

            # Agregar etiqueta de porcentaje fuera de la barra
            fig.add_trace(go.Scatter(
                x=[row["% Cobertura"] + 1 for _, row in cob.iterrows()],
                y=cob["Cliente"].tolist(),
                mode="text",
                text=[f"{p:.1f}%" for p in cob["% Cobertura"]],
                textfont=dict(color="#1A4731", size=10, family="monospace"),
                textposition="middle right",
                showlegend=False,
                hoverinfo="skip",
            ))

            fig.update_layout(
                **PLOT_LIGHT,
                xaxis=dict(title="% Cobertura", range=[0, 115], ticksuffix="%",
                           gridcolor=GRID_COLOR, color="#5F8B6E"),
                yaxis=dict(color="#5F8B6E"),
                font=PLOT_FONT,
                height=max(400, len(cob) * 30 + 80),
                margin=dict(l=10, r=60, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            if cod_contados > 0:
                dias_activos = df[df["Estado"] != "⏳ Pendiente"]["Fecha"].dt.date.nunique() if "Fecha" in df.columns else 1
                ritmo = cod_contados / max(dias_activos, 1)
                pendientes_u = universo_total - cod_contados
                meses = (pendientes_u / ritmo / 22) if ritmo > 0 else 0
                st.caption(
                    f"📐 Ritmo actual: {ritmo:.1f} códigos únicos/día activo · "
                    f"Pendientes: {pendientes_u:,} · "
                    f"Proyección al 100%: **~{meses:.1f} meses**"
                )

# ── TAB 2: EXACTITUD POR UBICACIÓN ────────────────────────────────────────────
with tab2:
    st.caption("Compara fila por fila: contado vs stock WMS en la misma ubicación. Detecta si el producto está donde el sistema dice.")
    if "Estado" not in df.columns or df.empty:
        st.info("Sin datos para mostrar.")
    else:
        res = df.groupby("Cliente").apply(
            lambda x: pd.Series({
                "OK": (x["Estado"] == "✅ OK").sum(),
                "Revisar": (x["Estado"] == "⚠ Revisar").sum(),
                "Ajuste": (x["Estado"] == "❌ Ajuste").sum(),
                "Pendiente": (x["Estado"] == "⏳ Pendiente").sum(),
                "Total": len(x),
            })
        ).reset_index()
        res["Contados"] = res["OK"] + res["Revisar"] + res["Ajuste"]
        res["Exactitud"] = (res["OK"] / res["Contados"] * 100).where(res["Contados"] > 0).round(1)
        res = res.dropna(subset=["Exactitud"]).sort_values("Exactitud", ascending=True)

        fig = px.bar(
            res, x="Exactitud", y="Cliente", orientation="h",
            color="Exactitud",
            color_continuous_scale=[[0, RED], [0.6, ORANGE], [1, GREEN_MID]],
            text="Exactitud",
            hover_data={"OK": True, "Revisar": True, "Ajuste": True, "Pendiente": True, "Contados": True},
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_coloraxes(showscale=False)
        fig.add_vline(x=85, line_dash="dot", line_color=GREEN_MID, opacity=0.6,
                      annotation_text="Meta 85%", annotation_font_color=GREEN_MID)
        fig.update_layout(
            **PLOT_LIGHT,
            xaxis=dict(title="Exactitud por ubicación %", range=[0, 115],
                       ticksuffix="%", gridcolor=GRID_COLOR, color="#5F8B6E"),
            yaxis=dict(color="#5F8B6E"),
            font=PLOT_FONT, showlegend=False,
            height=max(400, len(res) * 30 + 80),
            margin=dict(l=10, r=80, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Ver tabla detallada"):
            st.dataframe(
                res[["Cliente","OK","Revisar","Ajuste","Pendiente","Contados","Exactitud"]]
                .sort_values("Exactitud"),
                use_container_width=True, hide_index=True,
            )

# ── TAB 3: EXACTITUD POR SKU ──────────────────────────────────────────────────
with tab3:
    st.caption("Suma todo lo contado por código SKU y lo compara con el total WMS del mismo código. Un SKU es OK si el total cuadra aunque esté en otra ubicación.")
    if "Código SKU" not in df.columns or "Contado" not in df.columns or df.empty:
        st.info("Sin datos para mostrar.")
    else:
        df_cont_sku = df[df["Contado"].notna()].copy()
        if df_cont_sku.empty:
            st.info("No hay conteos registrados aún.")
        else:
            por_sku = df_cont_sku.groupby(["Código SKU", "Cliente"]).agg(
                Total_contado=("Contado", "sum"),
                Total_WMS=("Stock WMS", "sum"),
                Ubicaciones=("Ubicación", "nunique") if "Ubicación" in df_cont_sku.columns else ("Código SKU", "count"),
            ).reset_index()
            por_sku["Diferencia"] = por_sku["Total_contado"] - por_sku["Total_WMS"]
            por_sku["Estado SKU"] = por_sku["Diferencia"].apply(
                lambda d: "✅ OK" if d == 0 else ("⚠ Revisar" if abs(d) <= 2 else "❌ Ajuste")
            )

            # Resumen por cliente
            res_cli_sku = por_sku.groupby("Cliente").apply(
                lambda x: pd.Series({
                    "SKUs OK": (x["Estado SKU"] == "✅ OK").sum(),
                    "SKUs Revisar": (x["Estado SKU"] == "⚠ Revisar").sum(),
                    "SKUs Ajuste": (x["Estado SKU"] == "❌ Ajuste").sum(),
                    "Total SKUs": len(x),
                })
            ).reset_index()
            res_cli_sku["Exactitud SKU"] = (
                res_cli_sku["SKUs OK"] / res_cli_sku["Total SKUs"] * 100
            ).round(1)
            res_cli_sku = res_cli_sku.sort_values("Exactitud SKU", ascending=True)

            fig = px.bar(
                res_cli_sku, x="Exactitud SKU", y="Cliente", orientation="h",
                color="Exactitud SKU",
                color_continuous_scale=[[0, RED], [0.6, ORANGE], [1, GREEN_MID]],
                text="Exactitud SKU",
                hover_data={"SKUs OK": True, "SKUs Revisar": True, "SKUs Ajuste": True, "Total SKUs": True},
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_coloraxes(showscale=False)
            fig.add_vline(x=85, line_dash="dot", line_color=GREEN_MID, opacity=0.6,
                          annotation_text="Meta 85%", annotation_font_color=GREEN_MID)
            fig.update_layout(
                **PLOT_LIGHT,
                xaxis=dict(title="Exactitud por SKU %", range=[0, 115],
                           ticksuffix="%", gridcolor=GRID_COLOR, color="#5F8B6E"),
                yaxis=dict(color="#5F8B6E"),
                font=PLOT_FONT, showlegend=False,
                height=max(400, len(res_cli_sku) * 30 + 80),
                margin=dict(l=10, r=80, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Ver detalle por código SKU"):
                st.dataframe(
                    por_sku[["Código SKU","Cliente","Total_WMS","Total_contado","Diferencia","Ubicaciones","Estado SKU"]]
                    .sort_values("Diferencia", key=abs, ascending=False),
                    use_container_width=True, hide_index=True,
                )

# ── TAB 4: CUMPLIMIENTO DIARIO ────────────────────────────────────────────────
with tab4:
    if "Fecha" not in df.columns or "Estado" not in df.columns or df.empty:
        st.info("Sin datos para mostrar.")
    else:
        diario = df.groupby(df["Fecha"].dt.date).agg(
            Total=("Estado", "count"),
            Contados=("Estado", lambda x: (x != "⏳ Pendiente").sum()),
        ).reset_index()
        diario.columns = ["Fecha", "Total", "Contados"]
        diario["% Cumplimiento"] = (diario["Contados"] / diario["Total"] * 100).round(1)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=diario["Fecha"], y=diario["% Cumplimiento"],
            mode="lines+markers",
            line=dict(color=GREEN_MID, width=2),
            fill="tozeroy", fillcolor="rgba(46,125,50,0.08)",
            marker=dict(
                color=[RED if v == 0 else GREEN_MID for v in diario["% Cumplimiento"]],
                size=8, line=dict(color="white", width=1)
            ),
            hovertemplate="<b>%{x}</b><br>Cumplimiento: %{y:.1f}%<extra></extra>",
        ))
        fig.add_hline(y=80, line_dash="dot", line_color=GREEN_MID, opacity=0.5,
                      annotation_text="Meta 80%", annotation_font_color=GREEN_MID)
        fig.update_layout(
            **PLOT_LIGHT,
            xaxis=dict(title="", gridcolor=GRID_COLOR, color="#5F8B6E"),
            yaxis=dict(title="% Cumplimiento", range=[0, 105],
                       ticksuffix="%", gridcolor=GRID_COLOR, color="#5F8B6E"),
            font=PLOT_FONT, showlegend=False, height=380,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        prom = (diario["Contados"].sum() / diario["Total"].sum() * 100)
        dias_0 = (diario["% Cumplimiento"] == 0).sum()
        prom_s = diario[diario["% Cumplimiento"] > 0]["% Cumplimiento"].mean()
        c1, c2, c3 = st.columns(3)
        c1.metric("Promedio ponderado", f"{prom:.1f}%")
        c2.metric("Días con 0%", f"{dias_0}")
        c3.metric("Promedio sin días 0%", f"{prom_s:.1f}%" if not pd.isna(prom_s) else "—")

# ── TAB 5: EXACTITUD DIARIA ───────────────────────────────────────────────────
with tab5:
    if "Fecha" not in df.columns or "Estado" not in df.columns or df.empty:
        st.info("Sin datos para mostrar.")
    else:
        ev = df[df["Estado"] != "⏳ Pendiente"].groupby(df["Fecha"].dt.date).agg(
            Contados=("Estado", "count"),
            OK=("Estado", lambda x: (x == "✅ OK").sum()),
        ).reset_index()
        ev.columns = ["Fecha", "Contados", "OK"]
        ev["Exactitud"] = (ev["OK"] / ev["Contados"] * 100).round(1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=ev["Fecha"], y=ev["Contados"],
            name="Filas contadas",
            marker_color="rgba(46,125,50,0.20)",
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Filas contadas: %{y}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=ev["Fecha"], y=ev["Exactitud"],
            name="Exactitud ubicación %",
            mode="lines+markers",
            line=dict(color=GREEN_DARK, width=2),
            marker=dict(color=GREEN_DARK, size=6),
            hovertemplate="<b>%{x}</b><br>Exactitud: %{y:.1f}%<extra></extra>",
        ))
        fig.update_layout(
            **PLOT_LIGHT,
            xaxis=dict(gridcolor=GRID_COLOR, color="#5F8B6E"),
            yaxis=dict(title="Exactitud %", range=[0, 105], ticksuffix="%",
                       gridcolor=GRID_COLOR, color="#5F8B6E"),
            yaxis2=dict(title="Filas contadas", overlaying="y", side="right",
                        color="#5F8B6E", gridcolor="rgba(0,0,0,0)"),
            font=PLOT_FONT,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
            height=380, margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 6: TOP SKUs PROBLEMA ──────────────────────────────────────────────────
with tab6:
    if "Estado" not in df.columns or "Código SKU" not in df.columns or df.empty:
        st.info("Sin datos para mostrar.")
    else:
        ajustes_df = df[df["Estado"].isin(["❌ Ajuste", "⚠ Revisar"])].copy()
        if ajustes_df.empty:
            st.success("✅ No hay SKUs con ajustes en el período seleccionado.")
        else:
            if "Diferencia" in ajustes_df.columns:
                ajustes_df["Diferencia"] = pd.to_numeric(ajustes_df["Diferencia"], errors="coerce")
            top = ajustes_df.groupby(["Código SKU", "Cliente"]).agg(
                Veces=("Estado", "count"),
                Dif_prom=("Diferencia", "mean") if "Diferencia" in ajustes_df.columns else ("Estado", "count"),
            ).reset_index().sort_values("Veces", ascending=False).head(20)
            top.columns = ["Código SKU", "Cliente", "Veces con ajuste", "Diferencia prom."]
            top["Diferencia prom."] = top["Diferencia prom."].round(1)
            st.dataframe(top, use_container_width=True, hide_index=True,
                column_config={
                    "Veces con ajuste": st.column_config.NumberColumn(format="%d"),
                    "Diferencia prom.": st.column_config.NumberColumn(format="%.1f"),
                }
            )

            # SKUs siempre en 0
            if "Contado" in df.columns:
                df_c = df.copy()
                df_c["Contado_num"] = pd.to_numeric(df_c["Contado"], errors="coerce")
                siempre_0 = df_c[df_c["Contado_num"].notna()].groupby("Código SKU").apply(
                    lambda x: (x["Contado_num"] == 0).all() and len(x) >= 3
                )
                siempre_0 = siempre_0[siempre_0].index.tolist()
                if siempre_0:
                    st.warning(
                        f"⚠️ {len(siempre_0)} código(s) con conteo = 0 en todos sus registros: "
                        f"{', '.join(str(s) for s in siempre_0[:5])}{'...' if len(siempre_0) > 5 else ''}. "
                        "Posibles SKUs descontinuados activos en el sistema."
                    )

# ─── FOOTER ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Sistema de Inventario Cíclico · Cargoflex Supply · Datos en tiempo real desde Google Sheets.")

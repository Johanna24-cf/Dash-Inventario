"""
Dashboard Inventario Cíclico — Cargoflex
=========================================
Lee en tiempo real desde dos Google Sheets:
  - HISTORIAL-INVENTARIO-CICLICO (pestañas HIST_AAAA_MM)
  - Reporte Stock WMS Diario (Hoja 1)

Despliegue: Streamlit Cloud + GitHub
Credenciales: st.secrets["gcp_service_account"]
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2 import service_account
import gspread
from datetime import datetime, timedelta
import re

# ─── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Inventario Cíclico · Cargoflex",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0F1117; }
  [data-testid="stSidebar"] { background: #161B22; border-right: 1px solid #21262D; }
  .metric-card {
    background: #161B22; border: 1px solid #21262D; border-radius: 10px;
    padding: 16px 20px; text-align: center;
  }
  .metric-label { font-size: 12px; color: #8B949E; margin: 0 0 6px; text-transform: uppercase; letter-spacing: .5px; }
  .metric-value { font-size: 28px; font-weight: 700; margin: 0; line-height: 1.2; }
  .metric-sub   { font-size: 11px; color: #6E7681; margin: 4px 0 0; }
  .c-ok   { color: #3FB950; }
  .c-warn { color: #D29922; }
  .c-err  { color: #F85149; }
  .c-neu  { color: #E6EDF3; }
  .alert-box {
    border-radius: 8px; padding: 12px 16px;
    display: flex; gap: 10px; margin-bottom: 10px;
  }
  .alert-red  { background: rgba(248,81,73,0.12); border-left: 3px solid #F85149; }
  .alert-warn { background: rgba(210,153,34,0.12); border-left: 3px solid #D29922; }
  .alert-title { font-size: 13px; font-weight: 600; margin: 0 0 3px; }
  .alert-body  { font-size: 12px; color: #8B949E; margin: 0; }
  .section-title { font-size: 13px; font-weight: 600; color: #8B949E;
    text-transform: uppercase; letter-spacing: .5px; margin: 20px 0 10px; }
  div[data-testid="stSelectbox"] label { font-size: 13px !important; color: #8B949E !important; }
</style>
""", unsafe_allow_html=True)

# ─── Constantes ───────────────────────────────────────────────────────────────
CLIENTES_BODEGA = {
    'G & R': 'Cargoflex 1', 'G&G': 'Cargoflex 1', 'GOOD PERU': 'Cargoflex 1',
    'HAI VENTURES CORP S.A.C.': 'Cargoflex 1', 'INTERQUIMICA': 'Cargoflex 1',
    'LA CARCASA MOVIL': 'Cargoflex 1', 'MAXELL': 'Cargoflex 1',
    'ATLANTIC BUSSINES': 'Cargoflex 1', 'BIRKENSTOCK': 'Cargoflex 1',
    'ABEVER VINOS Y LICORES S.A.C.': 'Cargoflex 2',
    'CCK IMPORTACIONES S.A.C.': 'Cargoflex 2',
    'CONCEPTO PLACER SOCIEDAD ANONIMA CERRADA - CONPLAC': 'Cargoflex 2',
    'EL ZONDA VINOS S.A.C.': 'Cargoflex 2',
    'EUROPA WINE SOCIETY S.A.C. - EWS S.A.C.': 'Cargoflex 2',
    'JACA IMPORTACIONES S.A.C.': 'Cargoflex 2',
    'LOCO IMPORT & EXPORT S.A.C.': 'Cargoflex 2',
    'La Revolucion': 'Cargoflex 2', 'THE WINE WAREHOUSE S.A.C.': 'Cargoflex 2',
    'TYRON IMPORT-EXPORT S.A.C.': 'Cargoflex 2', 'VINICENTANNI': 'Cargoflex 2',
    'VINOS DE CULTO S.A.C': 'Cargoflex 2',
    'VITA IMPORTADORES Y DISTRIBUIDORES S.A.C.': 'Cargoflex 2',
    'Romovi': 'Cargoflex 2', 'MASEF': 'Cargoflex 2',
    'CASA DE LA CARCASA': 'Cargoflex 1', 'IVL': 'Cargoflex 2', 'SAGA': 'Cargoflex 2',
}

UBICACIONES_EXCLUIR = ['C1-DSP-1', 'C1-REC-1']

# ─── Conexión Google Sheets ───────────────────────────────────────────────────
@st.cache_resource(ttl=300)
def get_gspread_client():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner="Actualizando historial...")
def cargar_historial():
    """Lee todas las pestañas HIST_AAAA_MM del Sheet de historial."""
    client = get_gspread_client()
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
    # Normalizar nombres de columnas
    df.columns = [c.strip() for c in df.columns]
    # Parsear fecha
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
    # Limpiar código SKU (quitar apóstrofo de forzado de texto)
    if "Código SKU" in df.columns:
        df["Código SKU"] = df["Código SKU"].astype(str).str.lstrip("'").str.strip()
    # Agregar bodega
    if "Cliente" in df.columns:
        df["Bodega"] = df["Cliente"].map(CLIENTES_BODEGA).fillna("Otra")
    return df


@st.cache_data(ttl=300, show_spinner="Actualizando stock WMS...")
def cargar_stock_wms():
    """Lee el reporte de stock diario desde Google Sheets."""
    client = get_gspread_client()
    sh = client.open_by_key(st.secrets["sheets"]["sheet_id_stock_wms"])
    ws = sh.worksheet(st.secrets["sheets"].get("nombre_hoja_stock", "Hoja 1"))
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df.columns = [c.strip() for c in df.columns]
    if "Familia" in df.columns:
        df["Bodega"] = df["Familia"].map(CLIENTES_BODEGA).fillna("Otra")
    # Filtrar ubicaciones excluidas
    if "Ubicación" in df.columns:
        df = df[~df["Ubicación"].isin(UBICACIONES_EXCLUIR)]
    # Solo stock > 0
    col_stock = next((c for c in df.columns if "Stock" in c and "Físico" in c), None)
    if col_stock:
        df[col_stock] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0)
        df = df[df[col_stock] > 0]
    return df


# ─── Helpers ──────────────────────────────────────────────────────────────────
def calcular_exactitud(df):
    """Exactitud = OK / (OK + Revisar + Ajuste), excluye Pendientes."""
    contados = df[df["Estado"] != "⏳ Pendiente"]
    ok = (contados["Estado"] == "✅ OK").sum()
    total_contados = len(contados)
    return (ok / total_contados * 100) if total_contados > 0 else 0, ok, total_contados


def filtrar_df(df, bodega, cliente):
    if bodega != "Todas":
        df = df[df["Bodega"] == bodega]
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


def alert(msg_title, msg_body, tipo="red"):
    cls = "alert-red" if tipo == "red" else "alert-warn"
    icon = "🔴" if tipo == "red" else "🟡"
    st.markdown(f"""
    <div class="alert-box {cls}">
      <span>{icon}</span>
      <div>
        <p class="alert-title">{msg_title}</p>
        <p class="alert-body">{msg_body}</p>
      </div>
    </div>""", unsafe_allow_html=True)


# ─── LAYOUT PRINCIPAL ─────────────────────────────────────────────────────────
st.markdown("## 📦 Inventario Cíclico · Cargoflex")
st.caption(f"Actualizado cada 5 min · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# Cargar datos
with st.spinner("Cargando datos..."):
    df_hist = cargar_historial()
    df_wms  = cargar_stock_wms()

if df_hist.empty:
    st.error("No se encontraron datos en el historial. Verifica los IDs de los Sheets en st.secrets.")
    st.stop()

# ─── SIDEBAR: FILTROS ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Filtros")
    st.divider()

    # Filtro de mes
    if "Fecha" in df_hist.columns:
        meses_disp = sorted(df_hist["Fecha"].dt.to_period("M").unique(), reverse=True)
        meses_str  = ["Todos"] + [str(m) for m in meses_disp]
        mes_sel    = st.selectbox("Mes", meses_str)
    else:
        mes_sel = "Todos"

    # Filtro bodega
    bodegas = ["Todas"] + sorted(df_hist["Bodega"].dropna().unique().tolist()) if "Bodega" in df_hist.columns else ["Todas"]
    bodega_sel = st.selectbox("Bodega", bodegas)

    # Filtro cliente (depende de bodega)
    df_temp = df_hist.copy()
    if bodega_sel != "Todas" and "Bodega" in df_temp.columns:
        df_temp = df_temp[df_temp["Bodega"] == bodega_sel]
    clientes = ["Todos"] + sorted(df_temp["Cliente"].dropna().unique().tolist()) if "Cliente" in df_temp.columns else ["Todos"]
    cliente_sel = st.selectbox("Cliente", clientes)

    st.divider()
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()

    st.caption("Los datos se actualizan automáticamente cada 5 minutos.")

# ─── APLICAR FILTROS ──────────────────────────────────────────────────────────
df = df_hist.copy()
if mes_sel != "Todos" and "Fecha" in df.columns:
    df = df[df["Fecha"].dt.to_period("M").astype(str) == mes_sel]
df = filtrar_df(df, bodega_sel, cliente_sel)

# ─── KPIs PRINCIPALES ─────────────────────────────────────────────────────────
st.markdown('<p class="section-title">Resumen del período</p>', unsafe_allow_html=True)

total_filas = len(df)
exactitud, ok, contados = calcular_exactitud(df)
pendientes = (df["Estado"] == "⏳ Pendiente").sum() if "Estado" in df.columns else 0
ajustes    = (df["Estado"] == "❌ Ajuste").sum() if "Estado" in df.columns else 0
pct_pend   = (pendientes / total_filas * 100) if total_filas > 0 else 0

# Cobertura del universo
col_fam = next((c for c in df_wms.columns if c in ["Familia"]), None)
col_cod = next((c for c in df_wms.columns if "Código" in c), None)
if col_fam and col_cod and not df_wms.empty:
    wms_f = df_wms.copy()
    if bodega_sel != "Todas":
        wms_f = wms_f[wms_f["Bodega"] == bodega_sel]
    if cliente_sel != "Todos":
        wms_f = wms_f[wms_f[col_fam] == cliente_sel]
    universo_total  = wms_f[col_cod].astype(str).nunique()
    if "Código SKU" in df.columns:
        cod_contados = df[df["Estado"] != "⏳ Pendiente"]["Código SKU"].astype(str).nunique()
    else:
        cod_contados = 0
    pct_cobertura = (cod_contados / universo_total * 100) if universo_total > 0 else 0
else:
    universo_total = 0; cod_contados = 0; pct_cobertura = 0

cols = st.columns(5)
with cols[0]:
    color = "c-err" if pct_cobertura < 20 else ("c-warn" if pct_cobertura < 60 else "c-ok")
    card("Cobertura universo", f"{pct_cobertura:.1f}%", f"{cod_contados:,} de {universo_total:,} códigos", color)
with cols[1]:
    color = "c-err" if exactitud < 60 else ("c-warn" if exactitud < 80 else "c-ok")
    card("Exactitud", f"{exactitud:.1f}%", f"{ok:,} OK de {contados:,} contados", color)
with cols[2]:
    cum = (contados / total_filas * 100) if total_filas > 0 else 0
    color = "c-err" if cum < 50 else ("c-warn" if cum < 80 else "c-ok")
    card("Cumplimiento", f"{cum:.1f}%", f"{contados:,} de {total_filas:,} filas", color)
with cols[3]:
    color = "c-err" if ajustes > 50 else ("c-warn" if ajustes > 10 else "c-ok")
    card("Ajustes", f"{ajustes:,}", f"{(ajustes/contados*100):.1f}% de lo contado" if contados else "—", color)
with cols[4]:
    color = "c-err" if pct_pend > 40 else ("c-warn" if pct_pend > 20 else "c-ok")
    card("Pendientes", f"{pendientes:,}", f"{pct_pend:.1f}% del total generado", color)

st.divider()

# ─── ALERTAS AUTOMÁTICAS ──────────────────────────────────────────────────────
if "Cliente" in df.columns and "Estado" in df.columns and len(df) > 0:
    # Clientes con exactitud crítica
    resumen_cli = df.groupby("Cliente").apply(
        lambda x: pd.Series({
            "ok": (x["Estado"] == "✅ OK").sum(),
            "contados": (x["Estado"] != "⏳ Pendiente").sum(),
            "pendientes": (x["Estado"] == "⏳ Pendiente").sum(),
            "total": len(x),
        })
    ).reset_index()
    resumen_cli["exactitud"] = resumen_cli.apply(
        lambda r: r["ok"] / r["contados"] * 100 if r["contados"] > 0 else None, axis=1
    )
    criticos = resumen_cli[resumen_cli["exactitud"] < 20].sort_values("exactitud")
    sin_conteo = resumen_cli[resumen_cli["contados"] == 0]

    if not criticos.empty:
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
    # Dias con 0% cumplimiento
    if "Fecha" in df.columns:
        dias_0 = df.groupby("Fecha").apply(
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

# ─── TABS PRINCIPALES ─────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Cobertura del universo",
    "✅ Exactitud por cliente",
    "📈 Cumplimiento diario",
    "📅 Evolución diaria",
    "⚠️ Top SKUs problema",
])

# ── TAB 1: COBERTURA DEL UNIVERSO ─────────────────────────────────────────────
with tab1:
    if df_wms.empty or col_fam is None or col_cod is None:
        st.info("No hay datos de stock WMS disponibles.")
    else:
        wms_f = df_wms.copy()
        if bodega_sel != "Todas":
            wms_f = wms_f[wms_f["Bodega"] == bodega_sel]
        if cliente_sel != "Todos":
            wms_f = wms_f[wms_f[col_fam] == cliente_sel]

        universo_por_cli = wms_f.groupby(col_fam)[col_cod].nunique().reset_index()
        universo_por_cli.columns = ["Cliente", "Universo"]

        hist_c = df[df["Estado"] != "⏳ Pendiente"] if "Estado" in df.columns else df
        contados_por_cli = hist_c.groupby("Cliente")["Código SKU"].nunique().reset_index() if "Código SKU" in hist_c.columns else pd.DataFrame(columns=["Cliente", "Contados"])
        contados_por_cli.columns = ["Cliente", "Contados"]

        cob = universo_por_cli.merge(contados_por_cli, on="Cliente", how="left").fillna(0)
        cob["Contados"] = cob["Contados"].astype(int)
        cob["% Cobertura"] = (cob["Contados"] / cob["Universo"] * 100).round(1)
        cob["Pendientes"] = cob["Universo"] - cob["Contados"]
        cob["Label"] = cob.apply(lambda r: f"{r['Contados']}/{r['Universo']}", axis=1)
        cob = cob.sort_values("% Cobertura", ascending=True)

        def color_cob(p):
            if p >= 50: return "#3FB950"
            if p >= 10: return "#D29922"
            return "#F85149"

        cob["Color"] = cob["% Cobertura"].apply(color_cob)

        fig = go.Figure()
        for _, row in cob.iterrows():
            fig.add_trace(go.Bar(
                x=[row["% Cobertura"]],
                y=[row["Cliente"]],
                orientation="h",
                marker_color=row["Color"],
                text=row["Label"],
                textposition="inside",
                textfont=dict(color="white", size=10),
                hovertemplate=f"<b>{row['Cliente']}</b><br>Contados: {row['Contados']}<br>Universo: {row['Universo']}<br>Cobertura: {row['% Cobertura']}%<extra></extra>",
                showlegend=False,
            ))

        fig.update_layout(
            barmode="stack",
            xaxis=dict(title="% Cobertura", range=[0, 100], ticksuffix="%",
                       gridcolor="#21262D", color="#8B949E"),
            yaxis=dict(color="#8B949E"),
            plot_bgcolor="#0F1117", paper_bgcolor="#0F1117",
            font=dict(color="#E6EDF3", size=11),
            height=max(400, len(cob) * 28 + 80),
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Proyección
        if cod_contados > 0 and universo_total > 0:
            dias_activos = df[df["Estado"] != "⏳ Pendiente"]["Fecha"].dt.date.nunique() if "Fecha" in df.columns else 1
            ritmo = cod_contados / max(dias_activos, 1)
            pendientes_universo = universo_total - cod_contados
            dias_necesarios = pendientes_universo / ritmo if ritmo > 0 else 0
            meses = dias_necesarios / 22
            st.caption(f"📐 Ritmo actual: {ritmo:.1f} códigos únicos/día activo · "
                       f"Pendientes: {pendientes_universo:,} · "
                       f"Proyección para cubrir el 100%: **~{meses:.1f} meses**")

# ── TAB 2: EXACTITUD POR CLIENTE ──────────────────────────────────────────────
with tab2:
    if "Estado" not in df.columns or "Cliente" not in df.columns or df.empty:
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
        res["Color"] = res["Exactitud"].apply(
            lambda x: "#3FB950" if x >= 85 else ("#D29922" if x >= 60 else "#F85149")
        )

        fig = px.bar(
            res, x="Exactitud", y="Cliente", orientation="h",
            color="Color", color_discrete_map="identity",
            text="Exactitud",
            hover_data={"OK": True, "Revisar": True, "Ajuste": True,
                        "Pendiente": True, "Contados": True, "Color": False},
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(
            xaxis=dict(title="Exactitud %", range=[0, 110], ticksuffix="%",
                       gridcolor="#21262D", color="#8B949E"),
            yaxis=dict(color="#8B949E"),
            plot_bgcolor="#0F1117", paper_bgcolor="#0F1117",
            font=dict(color="#E6EDF3", size=11),
            showlegend=False,
            height=max(400, len(res) * 30 + 80),
            margin=dict(l=10, r=80, t=30, b=10),
        )
        fig.add_vline(x=85, line_dash="dot", line_color="#3FB950", opacity=0.5,
                      annotation_text="Meta 85%", annotation_font_color="#3FB950")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Ver tabla detallada"):
            st.dataframe(
                res[["Cliente", "OK", "Revisar", "Ajuste", "Pendiente", "Contados", "Exactitud"]]
                .sort_values("Exactitud"),
                use_container_width=True, hide_index=True,
            )

# ── TAB 3: CUMPLIMIENTO DIARIO ────────────────────────────────────────────────
with tab3:
    if "Fecha" not in df.columns or "Estado" not in df.columns or df.empty:
        st.info("Sin datos para mostrar.")
    else:
        diario = df.groupby(df["Fecha"].dt.date).agg(
            Total=("Estado", "count"),
            Contados=("Estado", lambda x: (x != "⏳ Pendiente").sum()),
        ).reset_index()
        diario.columns = ["Fecha", "Total", "Contados"]
        diario["% Cumplimiento"] = (diario["Contados"] / diario["Total"] * 100).round(1)
        diario["Color"] = diario["% Cumplimiento"].apply(
            lambda x: "#F85149" if x == 0 else ("#D29922" if x < 80 else "#3FB950")
        )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=diario["Fecha"], y=diario["% Cumplimiento"],
            mode="lines+markers",
            line=dict(color="#7C3AED", width=2),
            fill="tozeroy", fillcolor="rgba(124,58,237,0.08)",
            marker=dict(
                color=diario["Color"], size=8, line=dict(color="#0F1117", width=1)
            ),
            hovertemplate="<b>%{x}</b><br>Cumplimiento: %{y:.1f}%<extra></extra>",
            name="Cumplimiento",
        ))
        fig.add_hline(y=80, line_dash="dot", line_color="#3FB950", opacity=0.5,
                      annotation_text="Meta 80%", annotation_font_color="#3FB950")
        fig.update_layout(
            xaxis=dict(title="", gridcolor="#21262D", color="#8B949E"),
            yaxis=dict(title="% Cumplimiento", range=[0, 105], ticksuffix="%",
                       gridcolor="#21262D", color="#8B949E"),
            plot_bgcolor="#0F1117", paper_bgcolor="#0F1117",
            font=dict(color="#E6EDF3", size=11),
            showlegend=False, height=380,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        prom_pond = (diario["Contados"].sum() / diario["Total"].sum() * 100)
        dias_0 = (diario["% Cumplimiento"] == 0).sum()
        prom_sin_0 = diario[diario["% Cumplimiento"] > 0]["% Cumplimiento"].mean()
        c1, c2, c3 = st.columns(3)
        c1.metric("Promedio ponderado", f"{prom_pond:.1f}%")
        c2.metric("Días con 0% cumplimiento", f"{dias_0}")
        c3.metric("Promedio sin días 0%", f"{prom_sin_0:.1f}%" if not pd.isna(prom_sin_0) else "—")

# ── TAB 4: EVOLUCIÓN DIARIA ───────────────────────────────────────────────────
with tab4:
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
            marker_color="rgba(56,139,253,0.25)",
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Filas: %{y}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=ev["Fecha"], y=ev["Exactitud"],
            name="Exactitud %",
            mode="lines+markers",
            line=dict(color="#388BFD", width=2),
            marker=dict(color="#388BFD", size=6),
            hovertemplate="<b>%{x}</b><br>Exactitud: %{y:.1f}%<extra></extra>",
        ))
        fig.update_layout(
            xaxis=dict(gridcolor="#21262D", color="#8B949E"),
            yaxis=dict(title="Exactitud %", range=[0, 105], ticksuffix="%",
                       gridcolor="#21262D", color="#8B949E"),
            yaxis2=dict(title="Filas contadas", overlaying="y", side="right",
                        color="#8B949E", gridcolor="rgba(0,0,0,0)"),
            plot_bgcolor="#0F1117", paper_bgcolor="#0F1117",
            font=dict(color="#E6EDF3", size=11),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
            height=380, margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 5: TOP SKUs PROBLEMA ──────────────────────────────────────────────────
with tab5:
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

            st.dataframe(
                top, use_container_width=True, hide_index=True,
                column_config={
                    "Veces con ajuste": st.column_config.NumberColumn(format="%d"),
                    "Diferencia prom.": st.column_config.NumberColumn(format="%.1f"),
                }
            )

            # Patrones: SKUs con 0 contado siempre
            if "Contado" in df.columns:
                siempre_0 = df.groupby("Código SKU").apply(
                    lambda x: (pd.to_numeric(x["Contado"], errors="coerce") == 0).all() and len(x) >= 3
                )
                siempre_0 = siempre_0[siempre_0].index.tolist()
                if siempre_0:
                    st.warning(f"⚠️ {len(siempre_0)} código(s) con conteo = 0 en todos sus registros: "
                               f"{', '.join(str(s) for s in siempre_0[:5])}{'...' if len(siempre_0) > 5 else ''}. "
                               "Posibles SKUs descontinuados activos en el sistema.")

# ─── FOOTER ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Sistema de Inventario Cíclico · Cargoflex Supply · Los datos se leen en tiempo real desde Google Sheets.")

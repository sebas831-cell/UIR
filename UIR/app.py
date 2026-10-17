import inspect
import re
import unicodedata
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# CONFIGURACIÓN
# ============================================================
# ---- Datos de la campaña: actualizar SOLO aquí en cada corte ----
CAMPANA = "FEN 2026-2027"
FECHA_CORTE = "15/10/2026"          # formato DD/MM/AAAA
TITULO_SITUACIONAL = f"ESTADO SITUACIONAL DE LAS ACTIVIDADES - {CAMPANA}"

# Las intervenciones desestimadas no generan impacto: si True, sus
# Km / Beneficiarios / Hectáreas se ponen en 0 para que no inflen los totales.
EXCLUIR_DESESTIMADAS_DEL_IMPACTO = True
UMBRAL_DIAS_ESTANCADO = 30          # días en "EN CONTRATACION" para marcar estancamiento
UMBRAL_ATRASO_PP = 10               # puntos porcentuales de atraso (real vs programado)

FECHA_CORTE_DT = pd.to_datetime(FECHA_CORTE, format="%d/%m/%Y")

st.set_page_config(
    page_title=f"Descolmatación FEN · Corte {FECHA_CORTE}",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# ESTILO GENERAL (TEMA VERDE EJECUTIVO)
# ============================================================
st.markdown("""
<style>
.stApp { background:#F1F8F5; }
.block-container { max-width: 1600px; padding: 1rem 2rem 2rem; }

.header {
    background: linear-gradient(135deg,#1B5E20,#2E7D32);
    color:white; padding:22px 28px; border-radius:14px;
    margin-bottom:16px;
    box-shadow:0 4px 12px rgba(27,94,32,0.15);
    display:flex; justify-content:space-between; align-items:center;
    gap:20px; flex-wrap:wrap;
}
.header h1 { margin:0; font-size:30px; color:white; }
.header p { margin:5px 0 0; opacity:.9; }
.header .situacional { font-size:16px; font-weight:700; letter-spacing:.4px; opacity:1; margin-top:10px; }
.header .badge-fecha {
    background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.45);
    border-radius:12px; padding:10px 20px; text-align:center; min-width:170px;
}
.header .badge-fecha .lbl { font-size:11px; letter-spacing:1px; opacity:.85; margin:0; }
.header .badge-fecha .fecha { font-size:26px; font-weight:800; margin:2px 0 0; opacity:1; }

.kpi {
    background:white; border:1px solid #C8E6C9; border-radius:12px;
    padding:14px 16px; height:100%; min-height:100px;
    box-shadow:0 2px 8px rgba(46,125,50,.06);
    display: flex; flex-direction: column; justify-content: center;
}
.kpi-label { color:#388E3C; font-size:11px; font-weight:700; text-transform: uppercase; }
.kpi-value { color:#1B5E20; font-size:24px; font-weight:800; margin-top:2px; }
.kpi-help { color:#558B2F; font-size:10.5px; font-style:italic; margin-top:2px; }

.section {
    color:#1B5E20; font-size:18px; font-weight:800;
    margin:22px 0 12px;
    border-bottom: 2px solid #C8E6C9;
    padding-bottom: 4px;
}

.alert-red { background:#FEF2F2; border-left:5px solid #DC2626; padding:12px; border-radius:8px; color:#7F1D1D; }
.alert-amber { background:#FFF7ED; border-left:5px solid #F59E0B; padding:12px; border-radius:8px; color:#78350F; }
.alert-green { background:#E8F5E9; border-left:5px solid #2E7D32; padding:12px; border-radius:8px; color:#1B5E20; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# PALETAS DE COLOR
# ============================================================
PALETA = [
    "#2E7D32", "#1565C0", "#EF6C00", "#6A1B9A", "#00838F", "#AD1457",
    "#8D6E63", "#558B2F", "#5C6BC0", "#C62828", "#00695C", "#9E9D24",
]

REGLAS_ESTADO = [
    ("DESESTIMADA", "#C62828"),                          # rojo
    ("RIESGO|RETRAS|OBSERV|PENDIENTE", "#E65100"),       # naranja
    ("CONTRATACION", "#E89B0C"),                         # ámbar
    ("CONTRATADO", "#00838F"),                           # turquesa
    ("EJECUCION", "#2E7D32"),                            # verde
    ("CONCLU|TERMIN|FINALIZ|LIQUID|CULMIN", "#1565C0"),  # azul
    ("SIN ESTADO", "#90A4AE"),                           # gris
]
FALLBACK_ESTADO = ["#6A1B9A", "#AD1457", "#5D4037", "#5C6BC0"]


def mapa_estados(estados):
    cmap, extra = {}, 0
    for e in sorted(estados):
        for patron, color in REGLAS_ESTADO:
            if re.search(patron, e):
                cmap[e] = color
                break
        else:
            cmap[e] = FALLBACK_ESTADO[extra % len(FALLBACK_ESTADO)]
            extra += 1
    return cmap


def mapa_categorias(valores):
    return {v: PALETA[i % len(PALETA)] for i, v in enumerate(sorted(valores))}


# ============================================================
# UTILIDADES
# ============================================================
def sin_acentos(texto: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)
    )


def clave_pq(p: str):
    # Ordenar por departamento y luego por el número del paquete (LIMA PQ 1, LIMA PQ 2, ...)
    m = re.search(r"\d+", p)
    num = int(m.group()) if m else 0
    depto = re.sub(r"\d+", "", p).strip()
    return (depto, num, p)


_PLOTLY_TIENE_WIDTH = "width" in inspect.signature(st.plotly_chart).parameters


def mostrar(fig):
    if _PLOTLY_TIENE_WIDTH:
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig, use_container_width=True)


def titulo(texto):
    return dict(text=texto, font=dict(size=15, color="#1B5E20"))


def pie(data, names, values, title, cmap=None, fmt="%{value:,.0f}", height=340):
    fig = px.pie(
        data,
        names=names,
        values=values,
        hole=0.45,
        color=names,
        color_discrete_map=cmap or {},
        color_discrete_sequence=PALETA,
    )
    fig.update_traces(
        texttemplate=fmt + "<br>(%{percent})",
        textposition="inside",
        insidetextorientation="horizontal",
        textfont=dict(color="white", size=12),
        marker=dict(line=dict(color="white", width=2)),
        hovertemplate="<b>%{label}</b><br>" + fmt + "<br>%{percent}<extra></extra>",
        sort=True,
    )
    fig.update_layout(
        title=titulo(title),
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor="white",
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02),
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


def barras(data, x, y, title, color_col=None, cmap=None, color=PALETA[0],
           fmt="%{y:,.0f}", height=340, orden=None):
    """Barras verticales. Si se da color_col, cada barra se colorea por esa columna."""
    if color_col:
        fig = px.bar(data, x=x, y=y, color=color_col, color_discrete_map=cmap or {})
    else:
        fig = px.bar(data, x=x, y=y, color_discrete_sequence=[color])
    fig.update_traces(texttemplate=fmt, textposition="outside", cliponaxis=False)
    fig.update_layout(
        title=titulo(title),
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(gridcolor="#E8F5E9"),
        legend=dict(orientation="h", y=-0.35, title=None),
    )
    fig.update_xaxes(type="category", categoryorder="array",
                     categoryarray=orden or list(data[x]), tickangle=-45)
    return fig


# ============================================================
# CARGA DE DATOS
# ============================================================
BASE = Path(__file__).resolve().parent
EXCEL = BASE / "EXCEL DS 164 EF.xlsx"
COLUMNAS_REQUERIDAS = ["Departamento", "Provincia", "Distrito", "Paquete", "Estado"]

# Columnas opcionales: cada bloque del dashboard se activa solo si existen en el Excel.
COL_AVANCE = ["Avance_Fisico_%", "Avance_Prog_%"]
COL_MONTOS = ["Monto_Contratado", "Monto_Ejecutado"]
COLUMNAS_NUMERICAS_OPC = COL_AVANCE + COL_MONTOS + ["Volumen_m3"]
COLUMNAS_FECHA_OPC = ["Fecha_Inicio", "Fecha_Fin_Prog", "Fecha_Fin_Real", "Fecha_Cambio_Estado"]


def normalizar_paquete(v):
    """'Lima PQ1', 'LIMA PQ 1' y 'Lima Pq. 1' -> 'LIMA PQ 1'. Todo lo que no sea
    'DEPTO PQ n' (vacío, 'DESESTIMADA', etc.) -> 'SIN PAQUETE'."""
    if pd.isna(v):
        return "SIN PAQUETE"
    t = re.sub(r"\s+", " ", sin_acentos(str(v)).upper().strip())
    m = re.match(r"^(.*?)\s*PQ\.?\s*(\d+)$", t)
    if not m:
        return "SIN PAQUETE"
    return f"{m.group(1).strip()} PQ {m.group(2)}".strip()


@st.cache_data
def cargar_excel(_mtime: float):
    data = pd.read_excel(EXCEL)
    data.columns = [str(c).strip() for c in data.columns]

    # Columnas sin encabezado: se descartan, pero se avisa si traían datos
    sin_titulo = [c for c in data.columns if c.startswith("Unnamed")]
    n_sin_titulo = int(data[sin_titulo].notna().sum().sum()) if sin_titulo else 0
    data = data.drop(columns=sin_titulo).dropna(axis=1, how="all").copy()

    ren = {}
    for c in data.columns:
        t = c.lower()
        if t == "ben":
            ren[c] = "Beneficiarios"
        elif t == "ha":
            ren[c] = "Hectareas"
        elif t == "km":
            ren[c] = "Km"
    data.rename(columns=ren, inplace=True)

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in data.columns]
    if faltantes:
        return data, faltantes, n_sin_titulo

    data["Departamento"] = data["Departamento"].fillna("SIN DEPARTAMENTO").astype(str).str.strip()
    data["Paquete"] = data["Paquete"].map(normalizar_paquete)
    data["Depto_PQ"] = data["Paquete"].str.replace(r"\s*PQ\s*\d+$", "", regex=True)
    data["Es_PQ"] = data["Paquete"].str.contains(r"PQ \d+$", regex=True)

    for c in ["Km", "Beneficiarios", "Hectareas"] + COLUMNAS_NUMERICAS_OPC:
        if c not in data.columns:
            if c in ("Km", "Beneficiarios", "Hectareas"):
                data[c] = 0
            continue
        data[c] = pd.to_numeric(data[c], errors="coerce")
        if c in ("Km", "Beneficiarios", "Hectareas"):
            data[c] = data[c].fillna(0)

    for c in COLUMNAS_FECHA_OPC:
        if c in data.columns:
            data[c] = pd.to_datetime(data[c], errors="coerce", dayfirst=True)

    data["Estado"] = (
        data["Estado"].fillna("SIN ESTADO").astype(str).str.strip().str.upper().map(sin_acentos)
        .str.replace("CONTRADO", "CONTRATADO", regex=False)   # typo frecuente en el Excel
    )

    if EXCLUIR_DESESTIMADAS_DEL_IMPACTO:
        des = data["Estado"].str.contains("DESESTIMADA", na=False)
        data.loc[des, ["Km", "Beneficiarios", "Hectareas"]] = 0

    return data, [], n_sin_titulo


if not EXCEL.exists():
    st.error(f"No se encontró el archivo: {EXCEL}")
    st.stop()

df0, faltantes, N_SIN_TITULO = cargar_excel(EXCEL.stat().st_mtime)
if faltantes:
    st.error(f"Al Excel le faltan estas columnas: {', '.join(faltantes)}")
    st.stop()

ORDEN_PQ = sorted(df0.loc[df0["Es_PQ"], "Paquete"].unique(), key=clave_pq)
CMAP_ESTADO = mapa_estados(df0["Estado"].unique())
CMAP_DEPTO = mapa_categorias(df0["Departamento"].dropna().unique())

# ============================================================
# HEADER
# ============================================================
st.markdown(f"""
<div class="header">
  <div>
    <h1>🌊 Descolmatación · Fenómeno El Niño (FEN)</h1>
    <p class="situacional">{TITULO_SITUACIONAL}</p>
    <p>Dashboard Ejecutivo PMO · paquetes por departamento · estado · impacto · territorio</p>
  </div>
  <div class="badge-fecha">
    <p class="lbl">INFORMACIÓN AL</p>
    <p class="fecha">{FECHA_CORTE}</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# FILTROS DINÁMICOS
# ============================================================
st.markdown('<div class="section">🔎 Filtros del portafolio</div>', unsafe_allow_html=True)
f1, f2, f3, f4, f5 = st.columns([1.1, 1.1, 1.1, 1.2, 1.2])


def opciones(frame, col, key=None):
    return sorted(frame[col].dropna().astype(str).unique().tolist(), key=key)


departamentos = f1.multiselect("Departamento", opciones(df0, "Departamento"), placeholder="Seleccionar opciones")
df_f1 = df0[df0["Departamento"].isin(departamentos)] if departamentos else df0

provincias = f2.multiselect("Provincia", opciones(df_f1, "Provincia"), placeholder="Seleccionar opciones")
df_f2 = df_f1[df_f1["Provincia"].isin(provincias)] if provincias else df_f1

distritos = f3.multiselect("Distrito", opciones(df_f2, "Distrito"), placeholder="Seleccionar opciones")

paquetes_disponibles = opciones(df_f2, "Paquete", key=clave_pq)
paquetes = f4.multiselect("Paquete", paquetes_disponibles, placeholder="Seleccionar opciones")

estados = f5.multiselect("Estado", opciones(df0, "Estado"), placeholder="Seleccionar opciones")

df = df0.copy()
if departamentos:
    df = df[df["Departamento"].isin(departamentos)]
if provincias:
    df = df[df["Provincia"].isin(provincias)]
if distritos:
    df = df[df["Distrito"].isin(distritos)]
if paquetes:
    df = df[df["Paquete"].isin(paquetes)]
if estados:
    df = df[df["Estado"].isin(estados)]

if df.empty:
    st.warning("No hay registros con los filtros seleccionados.")
    st.stop()

# Subconjunto con paquete real (excluye "SIN PAQUETE", p. ej. las desestimadas)
df_pq = df[df["Es_PQ"]]
orden_pkg = [p for p in ORDEN_PQ if p in set(df_pq["Paquete"])]


def tiene(*cols):
    return all(c in df.columns and df[c].notna().any() for c in cols)


# ============================================================
# CÁLCULO DE KPIS
# ============================================================
total = len(df)
ejecucion = int(df["Estado"].str.contains("EJECUCION", na=False).sum())
encontratacion = int(df["Estado"].str.contains("EN CONTRATACION", na=False).sum())
desestimadas = int(df["Estado"].str.contains("DESESTIMADA", na=False).sum())
contratado = int(df["Estado"].str.contains("CONTRATADO", na=False).sum())
culminadas = int(df["Estado"].str.contains("CULMINADO", na=False).sum())

benef = df["Beneficiarios"].sum()
ha = df["Hectareas"].sum()
km = df["Km"].sum()

paquetes_activos = df_pq["Paquete"].nunique()

# Seguimiento = problemas reales. "EN CONTRATACION" es un paso normal, NO es alerta roja.
RE_PROBLEMA = "DESESTIMADA|PENDIENTE|RIESGO|RETRAS|OBSERV"
atencion_mask = df["Estado"].str.contains(RE_PROBLEMA, regex=True, na=False)
atencion = int(atencion_mask.sum())

# ============================================================
# COMPONENTE KPI ESTILIZADO
# ============================================================
st.markdown('<div class="section">📌 Indicadores ejecutivos</div>', unsafe_allow_html=True)


def kpi(c, label, value, help_text=f"Acumulado al {FECHA_CORTE}"):
    c.markdown(
        f"""
        <div class="kpi">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


nota_imp = "Sin desestimadas" if EXCLUIR_DESESTIMADAS_DEL_IMPACTO else f"Acumulado al {FECHA_CORTE}"

fila1 = st.columns(5, gap="small")
kpi(fila1[0], "PAQUETES (DEPTO-PQ)", f"{paquetes_activos:,}", "Paquetes con intervenciones")
kpi(fila1[1], "INTERVENCIONES TOTALES", f"{total:,}", "Incluye desestimadas")
kpi(fila1[2], "CONTRATADOS", f"{contratado:,}", "Procesos adjudicados")
kpi(fila1[3], "POR CONTRATAR", f"{encontratacion:,}", "En proceso de selección")
kpi(fila1[4], "EN EJECUCIÓN", f"{ejecucion:,}", "Obras/Actividades activas")

st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

fila2 = st.columns(5, gap="small")
kpi(fila2[0], "CULMINADAS", f"{culminadas:,}", "Acumulado al corte")
kpi(fila2[1], "DESESTIMADAS", f"{desestimadas:,}", "Sin intervención")
kpi(fila2[2], "BENEFICIARIOS", f"{benef:,.0f}", nota_imp)
kpi(fila2[3], "HECTÁREAS", f"{ha:,.2f}", nota_imp)
kpi(fila2[4], "KILÓMETROS", f"{km:,.2f}", nota_imp)

# ============================================================
# PORTAFOLIO POR PAQUETE
# ============================================================
st.markdown('<div class="section">📦 Portafolio por paquete (por departamento)</div>', unsafe_allow_html=True)

if df_pq.empty:
    st.info("Con los filtros actuales no hay intervenciones asignadas a un paquete.")
else:
    pkg = (
        df_pq.assign(
            _ej=df_pq["Estado"].str.contains("EJECUCION", na=False).astype(int),
            _cu=df_pq["Estado"].str.contains("CULMINADO", na=False).astype(int),
        )
        .groupby("Paquete")
        .agg(
            Departamento=("Departamento", "first"),   # cada paquete pertenece a un solo departamento
            Intervenciones=("Paquete", "size"),
            En_ejecucion=("_ej", "sum"),
            Culminadas=("_cu", "sum"),
            Beneficiarios=("Beneficiarios", "sum"),
            Hectareas=("Hectareas", "sum"),
            Km=("Km", "sum"),
            Provincias=("Provincia", "nunique"),
        )
        .loc[orden_pkg]
        .reset_index()
    )

    c1, c2 = st.columns(2)
    with c1:
        mostrar(barras(pkg, "Paquete", "Intervenciones", "Intervenciones por paquete",
                       color_col="Departamento", cmap=CMAP_DEPTO, orden=orden_pkg))
    with c2:
        mostrar(barras(pkg, "Paquete", "Beneficiarios", "Beneficiarios por paquete",
                       color_col="Departamento", cmap=CMAP_DEPTO, orden=orden_pkg))

    with st.expander("Ver tabla resumen por paquete"):
        st.dataframe(
            pkg.rename(columns={"En_ejecucion": "En ejecución"}).style.format(
                {"Beneficiarios": "{:,.0f}", "Hectareas": "{:,.2f}", "Km": "{:,.2f}"}),
            hide_index=True,
        )

# ============================================================
# ESTADO DEL PORTAFOLIO
# ============================================================
st.markdown('<div class="section">📈 Estado del portafolio</div>', unsafe_allow_html=True)

e1, e2 = st.columns([1, 1.4])

with e1:
    est = df.groupby("Estado").size().reset_index(name="Registros")
    mostrar(pie(est, "Estado", "Registros", "Distribución por estado", cmap=CMAP_ESTADO))

with e2:
    if df_pq.empty:
        st.info("Sin paquetes para mostrar estados por paquete.")
    else:
        est_pkg = df_pq.groupby(["Paquete", "Estado"]).size().reset_index(name="Registros")
        fig = px.bar(
            est_pkg, x="Paquete", y="Registros", color="Estado",
            color_discrete_map=CMAP_ESTADO,
            category_orders={"Paquete": orden_pkg},
        )
        fig.update_layout(
            barmode="stack",
            title=titulo("Estados por paquete (n.º de intervenciones)"),
            height=340, margin=dict(l=10, r=10, t=50, b=10),
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis_title=None, yaxis_title=None, yaxis=dict(gridcolor="#E8F5E9"),
            showlegend=False,   # los colores son los mismos de la dona de la izquierda
        )
        fig.update_xaxes(type="category", categoryorder="array",
                         categoryarray=orden_pkg, tickangle=-45)
        mostrar(fig)

# Alertas
a1, a2, a3 = st.columns(3)
pct_atencion = atencion / total * 100 if total > 0 else 0
pct_ejec = ejecucion / total * 100 if total > 0 else 0

with a1:
    st.markdown(f"""
    <div class="alert-red"><b>REQUIEREN SEGUIMIENTO</b><br><br>
    {atencion:,} registros ({pct_atencion:.1f}%) están desestimados, pendientes
    o con riesgo/retraso.</div>
    """, unsafe_allow_html=True)

with a2:
    cuello = df_pq[df_pq["Estado"].str.contains("EN CONTRATACION|PENDIENTE|RIESGO|RETRAS|OBSERV",
                                                regex=True, na=False)]
    if len(cuello):
        top = cuello["Paquete"].value_counts()
        msg = (f"<b>{top.index[0]}</b> concentra {top.iloc[0]:,} intervenciones aún sin contratar "
               f"o con alerta: revisarlo primero.")
    else:
        msg = "No hay paquetes con intervenciones por contratar o con alerta con los filtros actuales."
    st.markdown(f'<div class="alert-amber"><b>PRIORIDAD PMO</b><br><br>{msg}</div>',
                unsafe_allow_html=True)

with a3:
    st.markdown(f"""
    <div class="alert-green"><b>AVANCE</b><br><br>
    {ejecucion:,} registros ({pct_ejec:.1f}%) se encuentran en ejecución.</div>
    """, unsafe_allow_html=True)

# ============================================================
# DISTRIBUCIÓN TERRITORIAL
# ============================================================
st.markdown('<div class="section">🗺️ Distribución territorial</div>', unsafe_allow_html=True)

NOMBRES_IND = {
    "Intervenciones": "Intervenciones",
    "Beneficiarios": "Beneficiarios",
    "Hectareas": "Hectáreas",
    "Km": "Km",
}

s1, s2 = st.columns(2)
indicador = s1.radio(
    "Indicador a evaluar", list(NOMBRES_IND), format_func=NOMBRES_IND.get, horizontal=True
)
deptos_disp = sorted(df["Departamento"].dropna().unique())
dept = s2.selectbox("Departamento para el detalle provincial", deptos_disp) if deptos_disp else None

fmt_ind = "%{value:,.0f}" if indicador in ("Intervenciones", "Beneficiarios") else "%{value:,.1f}"
nom = NOMBRES_IND[indicador]


def serie_por(frame, col):
    if indicador == "Intervenciones":
        s = frame.groupby(col).size().rename("Valor")
    else:
        s = frame.groupby(col)[indicador].sum().rename("Valor")
    return s[s > 0].reset_index()


t1, t2 = st.columns(2)

with t1:
    d = serie_por(df, "Departamento")
    if d.empty:
        st.warning(f"Sin datos de {nom} para los filtros actuales.")
    else:
        mostrar(pie(d, "Departamento", "Valor", f"{nom} por departamento",
                    cmap=CMAP_DEPTO, fmt=fmt_ind))

with t2:
    if dept:
        p = serie_por(df[df["Departamento"] == dept], "Provincia")
        if p.empty:
            st.warning(f"Sin datos de {nom} en {dept}.")
        else:
            mostrar(pie(p, "Provincia", "Valor", f"{nom} por provincia · {dept}", fmt=fmt_ind))
    else:
        st.info("Seleccione un departamento válido.")

if dept:
    df_dept = df[df["Departamento"] == dept]
    u1, u2 = st.columns(2)

    with u1:
        est_d = df_dept.groupby("Estado").size().reset_index(name="Registros")
        mostrar(pie(est_d, "Estado", "Registros", f"Estados de las intervenciones · {dept}",
                    cmap=CMAP_ESTADO))

    with u2:
        est_p = df_dept.groupby(["Provincia", "Estado"]).size().reset_index(name="Registros")
        fig = px.bar(
            est_p, y="Provincia", x="Registros", color="Estado", orientation="h",
            barmode="stack", color_discrete_map=CMAP_ESTADO,
        )
        fig.update_layout(
            title=titulo(f"Estados por provincia · {dept}"),
            height=340, margin=dict(l=10, r=10, t=50, b=10),
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis_title=None, yaxis_title=None, xaxis=dict(gridcolor="#E8F5E9"),
            legend=dict(orientation="h", y=-0.2, title=None),
        )
        mostrar(fig)

# ============================================================
# DETALLE POR PAQUETE
# ============================================================
st.markdown('<div class="section">🔍 Detalle por paquete</div>', unsafe_allow_html=True)

paquete_detalle = st.selectbox("Selecciona un paquete", orden_pkg) if orden_pkg else None

if paquete_detalle:
    det = df_pq[df_pq["Paquete"] == paquete_detalle]

    q1, q2, q3, q4 = st.columns(4)
    kpi(q1, "INTERVENCIONES", f"{len(det):,}", f"Acumulado al {FECHA_CORTE}")
    kpi(q2, "BENEFICIARIOS", f"{det['Beneficiarios'].sum():,.0f}", f"Acumulado al {FECHA_CORTE}")
    kpi(q3, "HECTÁREAS", f"{det['Hectareas'].sum():,.2f}", f"Acumulado al {FECHA_CORTE}")
    kpi(q4, "KILÓMETROS", f"{det['Km'].sum():,.2f}", f"Acumulado al {FECHA_CORTE}")

    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

    v1, v2 = st.columns(2)
    with v1:
        d_est = det.groupby("Estado").size().reset_index(name="Registros")
        mostrar(pie(d_est, "Estado", "Registros", f"Estados · {paquete_detalle}", cmap=CMAP_ESTADO))
    with v2:
        # El departamento es siempre el mismo dentro de un paquete: se muestra el distrito.
        d_dis = det.groupby("Distrito").size().reset_index(name="Registros")
        mostrar(pie(d_dis, "Distrito", "Registros", f"Distritos · {paquete_detalle}"))

    with st.expander(f"Ver intervenciones de {paquete_detalle}"):
        cols_det = [c for c in ["Provincia", "Distrito", "Sector", "Km", "Beneficiarios",
                                "Hectareas", "Estado"] if c in det.columns]
        st.dataframe(det[cols_det], hide_index=True)

# ============================================================
# BLOQUES OPCIONALES (se activan solos cuando el Excel trae las columnas)
# ============================================================
if not df_pq.empty and (tiene(*COL_AVANCE) or tiene(*COL_MONTOS)
                        or tiene("Fecha_Cambio_Estado") or tiene("Restriccion")):
    st.markdown('<div class="section">⏱️ Cronograma, costos y restricciones</div>',
                unsafe_allow_html=True)

    if tiene(*COL_AVANCE):
        av = (df_pq.groupby("Paquete")[COL_AVANCE].mean().reindex(orden_pkg).reset_index())
        av["Desviacion"] = av["Avance_Fisico_%"] - av["Avance_Prog_%"]
        largo = av.melt(id_vars="Paquete", value_vars=COL_AVANCE, var_name="Tipo", value_name="Avance %")
        largo["Tipo"] = largo["Tipo"].map({"Avance_Fisico_%": "Real", "Avance_Prog_%": "Programado"})
        fig = px.bar(largo, x="Paquete", y="Avance %", color="Tipo", barmode="group",
                     color_discrete_map={"Real": "#2E7D32", "Programado": "#90A4AE"})
        fig.update_layout(title=titulo("Avance físico: real vs programado (promedio por paquete)"),
                          height=340, margin=dict(l=10, r=10, t=50, b=10),
                          plot_bgcolor="white", paper_bgcolor="white",
                          xaxis_title=None, yaxis_title=None, yaxis=dict(gridcolor="#E8F5E9"),
                          legend=dict(orientation="h", y=-0.35, title=None))
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=orden_pkg, tickangle=-45)
        mostrar(fig)
        atrasados = av[av["Desviacion"] < -UMBRAL_ATRASO_PP].sort_values("Desviacion")
        if len(atrasados):
            lista = ", ".join(f"<b>{r.Paquete}</b> ({r.Desviacion:.0f} pp)" for r in atrasados.itertuples())
            st.markdown(f'<div class="alert-red"><b>PAQUETES ATRASADOS (&gt;{UMBRAL_ATRASO_PP} pp)</b><br><br>{lista}</div>',
                        unsafe_allow_html=True)

    if tiene(*COL_MONTOS):
        fin = df_pq.groupby("Paquete")[COL_MONTOS].sum().reindex(orden_pkg).reset_index()
        fin["Saldo"] = fin["Monto_Contratado"] - fin["Monto_Ejecutado"]
        fin["% Ejecución"] = (fin["Monto_Ejecutado"] / fin["Monto_Contratado"] * 100).where(
            fin["Monto_Contratado"] > 0)
        largo = fin.melt(id_vars="Paquete", value_vars=COL_MONTOS, var_name="Concepto", value_name="Monto")
        fig = px.bar(largo, x="Paquete", y="Monto", color="Concepto", barmode="group",
                     color_discrete_map={"Monto_Contratado": "#1565C0", "Monto_Ejecutado": "#2E7D32"})
        fig.update_layout(title=titulo("Monto contratado vs ejecutado por paquete"),
                          height=340, margin=dict(l=10, r=10, t=50, b=10),
                          plot_bgcolor="white", paper_bgcolor="white",
                          xaxis_title=None, yaxis_title=None, yaxis=dict(gridcolor="#E8F5E9"),
                          legend=dict(orientation="h", y=-0.35, title=None))
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=orden_pkg, tickangle=-45)
        mostrar(fig)
        with st.expander("Ver tabla financiera por paquete"):
            st.dataframe(fin.style.format({"Monto_Contratado": "{:,.0f}", "Monto_Ejecutado": "{:,.0f}",
                                           "Saldo": "{:,.0f}", "% Ejecución": "{:.1f}%"}),
                         hide_index=True)

    if tiene("Fecha_Cambio_Estado"):
        estanc = df_pq[df_pq["Estado"].str.contains("EN CONTRATACION", na=False)].copy()
        estanc["Dias_en_estado"] = (FECHA_CORTE_DT - estanc["Fecha_Cambio_Estado"]).dt.days
        estanc = estanc[estanc["Dias_en_estado"] > UMBRAL_DIAS_ESTANCADO].sort_values(
            "Dias_en_estado", ascending=False)
        st.markdown(
            f'<div class="alert-amber"><b>ESTANCADAS EN CONTRATACIÓN</b><br><br>'
            f'{len(estanc):,} intervenciones llevan más de {UMBRAL_DIAS_ESTANCADO} días en contratación.</div>',
            unsafe_allow_html=True)
        if len(estanc):
            with st.expander("Ver intervenciones estancadas"):
                cols_e = [c for c in ["Paquete", "Distrito", "Sector", "Dias_en_estado"] if c in estanc.columns]
                st.dataframe(estanc[cols_e], hide_index=True)

    if tiene("Restriccion"):
        rs = df_pq["Restriccion"].dropna().astype(str).str.strip()
        rs = rs[rs != ""].value_counts().reset_index()
        rs.columns = ["Restriccion", "Intervenciones"]
        if len(rs):
            mostrar(barras(rs, "Restriccion", "Intervenciones", "Restricciones más frecuentes",
                           color="#E65100", orden=list(rs["Restriccion"])))

# ============================================================
# CONTROL DE CALIDAD DE DATOS
# ============================================================
with st.expander("🧪 Control de calidad del Excel"):
    problemas = 0

    incons = df0[df0["Es_PQ"] & (df0["Depto_PQ"].map(sin_acentos)
                                 != df0["Departamento"].str.upper().map(sin_acentos))]
    if len(incons):
        problemas += 1
        st.warning(f"{len(incons)} intervenciones tienen un paquete que no corresponde a su departamento:")
        st.dataframe(incons[["Departamento", "Provincia", "Distrito", "Sector", "Paquete"]], hide_index=True)

    sin_pq = df0[~df0["Es_PQ"] & ~df0["Estado"].str.contains("DESESTIMADA", na=False)]
    if len(sin_pq):
        problemas += 1
        st.warning(f"{len(sin_pq)} intervenciones vigentes (no desestimadas) no tienen paquete asignado:")
        st.dataframe(sin_pq[["Departamento", "Provincia", "Distrito", "Sector", "Estado"]], hide_index=True)

    if "Sector" in df0.columns:
        dup = df0[df0.duplicated(["Distrito", "Sector"], keep=False)]
        if len(dup):
            problemas += 1
            st.warning(f"{len(dup)} filas comparten Distrito + Sector (posibles duplicados):")
            st.dataframe(dup[["Distrito", "Sector", "Paquete", "Estado"]].sort_values(["Distrito", "Sector"]),
                         hide_index=True)

    if N_SIN_TITULO:
        problemas += 1
        st.warning(f"Hay {N_SIN_TITULO} celdas con datos en columnas sin encabezado del Excel. "
                   "Se ignoraron: ponles nombre o bórralas.")

    n_des_pq = int(df0["Estado"].str.contains("DESESTIMADA", na=False).sum())
    st.caption(f"Desestimadas: {n_des_pq} · Paquetes con intervenciones: {df0.loc[df0['Es_PQ'], 'Paquete'].nunique()}")
    if problemas == 0:
        st.success("Sin inconsistencias detectadas.")

with st.expander("📝 Columnas que activarían más secciones del dashboard"):
    CATALOGO = {
        "Avance_Fisico_%": "Avance real (0-100)",
        "Avance_Prog_%": "Avance programado (0-100)",
        "Monto_Contratado": "Monto del contrato",
        "Monto_Ejecutado": "Monto ejecutado/valorizado",
        "Fecha_Cambio_Estado": "Fecha en que pasó al estado actual",
        "Restriccion": "Lista cerrada: permiso ANA, predio/acceso, maquinaria, clima, conflicto social, otro",
        "Volumen_m3": "Volumen descolmatado",
    }
    faltan = {k: v for k, v in CATALOGO.items() if k not in df0.columns}
    if faltan:
        st.markdown("\n".join(f"- **{k}**: {v}" for k, v in faltan.items()))
        st.caption("Cada bloque se activa solo cuando existen sus columnas; el dashboard no inventa datos.")
    else:
        st.success("El Excel ya trae todas las columnas opcionales.")

# ============================================================
# FOOTER
# ============================================================
st.caption(
    f"Descolmatación · {CAMPANA} · Información acumulada al {FECHA_CORTE} (corte en desarrollo) · "
    "Fuente: EXCEL DS 164 EF.xlsx · Agrupación por paquete departamental "
    "(ej.: LIMA PQ 1, PIURA PQ 2, etc.)."
)

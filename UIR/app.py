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
}
.header {
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
    padding:15px 18px; min-height:105px;
    box-shadow:0 2px 8px rgba(46,125,50,.06);
}
.kpi-label { color:#388E3C; font-size:12px; font-weight:700; }
.kpi-value { color:#1B5E20; font-size:27px; font-weight:800; margin-top:3px; }
.kpi-help { color:#66A36B; font-size:11px; }

.section {
    color:#1B5E20; font-size:18px; font-weight:800;
    margin:22px 0 8px;
    border-bottom: 2px solid #C8E6C9;
    padding-bottom: 4px;
}

.alert-red { background:#FEF2F2; border-left:5px solid #DC2626; padding:12px; border-radius:8px; color:#7F1D1D; }
.alert-amber { background:#FFF7ED; border-left:5px solid #F59E0B; padding:12px; border-radius:8px; color:#78350F; }
.alert-green { background:#E8F5E9; border-left:5px solid #2E7D32; padding:12px; border-radius:8px; color:#1B5E20; }

div[data-testid="stMetric"] {
    background:white; border:1px solid #C8E6C9; padding:12px;
    border-radius:12px;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# PALETAS DE COLOR
# ============================================================
# Paleta categórica: tonos medios/oscuros (el texto blanco se lee bien)
# y distinguibles entre sí, en armonía con el tema verde.
PALETA = [
    "#2E7D32", "#1565C0", "#EF6C00", "#6A1B9A", "#00838F", "#AD1457",
    "#8D6E63", "#558B2F", "#5C6BC0", "#C62828", "#00695C", "#9E9D24",
]

# Colores con significado para el Estado (semáforo)
REGLAS_ESTADO = [
    ("DESESTIMADA", "#C62828"),                          # rojo
    ("RIESGO|RETRAS|OBSERV|PENDIENTE", "#E65100"),       # naranja
    ("CONTRATACION", "#E89B0C"),                         # ámbar
    ("EJECUCION", "#2E7D32"),                            # verde
    ("CONCLU|TERMIN|FINALIZ|LIQUID|CULMIN", "#1565C0"),  # azul
    ("SIN ESTADO", "#90A4AE"),                           # gris
]
FALLBACK_ESTADO = ["#6A1B9A", "#00838F", "#AD1457", "#5D4037", "#5C6BC0"]


def mapa_estados(estados):
    """Asigna un color fijo y con significado a cada estado."""
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
    """Color estable por categoría (el mismo departamento = mismo color en todos los gráficos)."""
    return {v: PALETA[i % len(PALETA)] for i, v in enumerate(sorted(valores))}


# ============================================================
# UTILIDADES
# ============================================================
def sin_acentos(texto: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)
    )


def clave_pq(p: str):
    """Ordena PQ 1, PQ 2, ..., PQ 10 numéricamente; el resto al final."""
    m = re.search(r"\d+", p)
    return (0, int(m.group()), p) if m and p.startswith("PQ") else (1, 0, p)


_PLOTLY_TIENE_WIDTH = "width" in inspect.signature(st.plotly_chart).parameters


def mostrar(fig):
    """Compatible con versiones nuevas y antiguas de Streamlit."""
    if _PLOTLY_TIENE_WIDTH:
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig, use_container_width=True)


def titulo(texto):
    return dict(text=texto, font=dict(size=15, color="#1B5E20"))


def pie(data, names, values, title, cmap=None, fmt="%{value:,.0f}", height=340):
    """Gráfico circular con colores distinguibles, etiquetas legibles y leyenda lateral."""
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
        uniformtext_mode="hide",  # oculta etiquetas de porciones muy pequeñas
    )
    return fig


def barras(data, x, y, title, color=PALETA[0], fmt="%{y:,.0f}", height=320, orden=None):
    fig = px.bar(data, x=x, y=y, title=title, color_discrete_sequence=[color])
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
    )
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=orden or list(data[x]))
    return fig


# ============================================================
# CARGA
# ============================================================
BASE = Path(__file__).resolve().parent
EXCEL = BASE / "EXCEL DS 164 EF.xlsx"
COLUMNAS_REQUERIDAS = ["Departamento", "Provincia", "Distrito", "Paquete", "Estado"]


@st.cache_data
def cargar_excel(_mtime: float):
    data = pd.read_excel(EXCEL)
    data = data.dropna(axis=1, how="all").copy()

    ren = {}
    for c in data.columns:
        t = str(c).strip().lower()
        if t == "ben":
            ren[c] = "Beneficiarios"
        elif t == "ha":
            ren[c] = "Hectareas"
        elif t == "km":
            ren[c] = "Km"
    data.rename(columns=ren, inplace=True)

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in data.columns]
    if faltantes:
        return data, faltantes

    def normalizar_paquete(v):
        if pd.isna(v) or str(v).strip() == "":
            return "SIN PAQUETE"
        s = str(v).strip().upper()
        m = re.search(r"\bPQ\s*[-_]?\s*(\d+)\b", s)
        return f"PQ {m.group(1)}" if m else s

    data["Paquete"] = data["Paquete"].map(normalizar_paquete)

    for c in ["Km", "Beneficiarios", "Hectareas"]:
        if c not in data.columns:
            data[c] = 0
        data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0)

    # Estado en mayúsculas y SIN acentos (EJECUCIÓN == EJECUCION)
    data["Estado"] = (
        data["Estado"].fillna("SIN ESTADO").astype(str).str.strip().str.upper().map(sin_acentos)
    )
    return data, []


if not EXCEL.exists():
    st.error(f"No se encontró el archivo: {EXCEL}")
    st.stop()

df0, faltantes = cargar_excel(EXCEL.stat().st_mtime)
if faltantes:
    st.error(f"Al Excel le faltan estas columnas: {', '.join(faltantes)}")
    st.stop()

ORDEN_PQ = sorted(df0["Paquete"].unique(), key=clave_pq)
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
    <p>Dashboard Ejecutivo PMO · paquetes · estado · impacto · territorio</p>
  </div>
  <div class="badge-fecha">
    <p class="lbl">INFORMACIÓN AL</p>
    <p class="fecha">{FECHA_CORTE}</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# FILTROS (en cascada: Departamento → Provincia → Distrito)
# ============================================================
st.markdown('<div class="section">🔎 Filtros del portafolio</div>', unsafe_allow_html=True)
f1, f2, f3, f4, f5 = st.columns([1.1, 1.1, 1.1, 1.2, 1.2])


def opciones(frame, col, key=None):
    return sorted(frame[col].dropna().astype(str).unique().tolist(), key=key)


departamentos = f1.multiselect("Departamento", opciones(df0, "Departamento"))
d1 = df0[df0["Departamento"].isin(departamentos)] if departamentos else df0

provincias = f2.multiselect("Provincia", opciones(d1, "Provincia"))
d2 = d1[d1["Provincia"].isin(provincias)] if provincias else d1

distritos = f3.multiselect("Distrito", opciones(d2, "Distrito"))
paquetes = f4.multiselect("Paquete", opciones(df0, "Paquete", key=clave_pq))
estados = f5.multiselect("Estado", opciones(df0, "Estado"))

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

# ============================================================
# KPIs
# ============================================================
total = len(df)
ejecucion = int(df["Estado"].str.contains("EJECUCION", na=False).sum())
contratacion = int(df["Estado"].str.contains("CONTRATACION", na=False).sum())
desestimadas = int(df["Estado"].str.contains("DESESTIMADA", na=False).sum())
benef = df["Beneficiarios"].sum()
ha = df["Hectareas"].sum()
km = df["Km"].sum()
paquetes_activos = df.loc[df["Paquete"].str.match(r"^PQ \d+$"), "Paquete"].nunique()

atencion_mask = df["Estado"].str.contains(
    "CONTRATACION|DESESTIMADA|PENDIENTE|RIESGO|RETRAS|OBSERV", regex=True, na=False
)
atencion = int(atencion_mask.sum())

st.markdown('<div class="section">📌 Indicadores ejecutivos</div>', unsafe_allow_html=True)
k = st.columns(8)


def kpi(c, label, value):
    c.markdown(f"""
    <div class="kpi">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


kpi(k[0], "PAQUETES", f"{paquetes_activos}")
kpi(k[1], "REGISTROS", f"{total:,}")
kpi(k[2], "EN EJECUCIÓN", f"{ejecucion:,}")
kpi(k[3], "EN CONTRATACIÓN", f"{contratacion:,}")
kpi(k[4], "DESESTIMADAS", f"{desestimadas:,}")
kpi(k[5], "BENEFICIARIOS", f"{benef:,.0f}")
kpi(k[6], "HECTÁREAS", f"{ha:,.2f}")
kpi(k[7], "KM", f"{km:,.2f}")

# ============================================================
# PORTAFOLIO POR PAQUETE
# ============================================================
st.markdown('<div class="section">📦 Portafolio por paquete</div>', unsafe_allow_html=True)

pkg = (
    df.groupby("Paquete")
    .agg(
        Intervenciones=("Paquete", "size"),
        Beneficiarios=("Beneficiarios", "sum"),
        Hectareas=("Hectareas", "sum"),
        Km=("Km", "sum"),
        Departamentos=("Departamento", "nunique"),
        Provincias=("Provincia", "nunique"),
    )
    .reset_index()
)
orden_pkg = [p for p in ORDEN_PQ if p in set(pkg["Paquete"])]
pkg = pkg.set_index("Paquete").loc[orden_pkg].reset_index()

c1, c2 = st.columns(2)
with c1:
    mostrar(barras(pkg, "Paquete", "Intervenciones", "Intervenciones por paquete",
                   color="#2E7D32", orden=orden_pkg))
with c2:
    mostrar(barras(pkg, "Paquete", "Beneficiarios", "Beneficiarios por paquete",
                   color="#1565C0", orden=orden_pkg))

with st.expander("Ver tabla resumen por paquete"):
    st.dataframe(
        pkg.style.format({"Beneficiarios": "{:,.0f}", "Hectareas": "{:,.2f}", "Km": "{:,.2f}"}),
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
    est_pkg = df.groupby(["Paquete", "Estado"]).size().reset_index(name="Registros")
    fig = px.bar(
        est_pkg, x="Paquete", y="Registros", color="Estado", barmode="stack",
        color_discrete_map=CMAP_ESTADO,
        category_orders={"Paquete": orden_pkg},
    )
    fig.update_layout(
        title=titulo("Estados por paquete"),
        height=340, margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis_title=None, yaxis_title=None, yaxis=dict(gridcolor="#E8F5E9"),
        legend=dict(orientation="h", y=-0.2, title=None),
    )
    mostrar(fig)

# Alertas con datos reales (en lugar de textos genéricos)
a1, a2, a3 = st.columns(3)
pct_atencion = atencion / total * 100
pct_ejec = ejecucion / total * 100

with a1:
    st.markdown(f"""
    <div class="alert-red"><b>REQUIEREN SEGUIMIENTO</b><br><br>
    {atencion:,} registros ({pct_atencion:.1f}%) están en contratación, pendientes,
    con riesgo/retraso o desestimados.</div>
    """, unsafe_allow_html=True)

with a2:
    if atencion:
        top = df.loc[atencion_mask, "Paquete"].value_counts()
        msg = f"<b>{top.index[0]}</b> concentra {top.iloc[0]:,} registros en seguimiento: revisarlo primero."
    else:
        msg = "No hay registros en seguimiento con los filtros actuales."
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
dept = s2.selectbox("Departamento para el detalle provincial", deptos_disp)

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
    p = serie_por(df[df["Departamento"] == dept], "Provincia")
    if p.empty:
        st.warning(f"Sin datos de {nom} en {dept}.")
    else:
        mostrar(pie(p, "Provincia", "Valor", f"{nom} por provincia · {dept}", fmt=fmt_ind))

# Estados dentro del departamento elegido (mismo selector, sin repetir controles)
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

opciones_pq = [p for p in ORDEN_PQ if p in set(df["Paquete"])]
paquete_detalle = st.selectbox("Selecciona un paquete", opciones_pq)

det = df[df["Paquete"] == paquete_detalle]

q1, q2, q3, q4 = st.columns(4)
q1.metric("Intervenciones", f"{len(det):,}")
q2.metric("Beneficiarios", f"{det['Beneficiarios'].sum():,.0f}")
q3.metric("Ha", f"{det['Hectareas'].sum():,.2f}")
q4.metric("Km", f"{det['Km'].sum():,.2f}")

v1, v2 = st.columns(2)
with v1:
    d_est = det.groupby("Estado").size().reset_index(name="Registros")
    mostrar(pie(d_est, "Estado", "Registros", f"Estados · {paquete_detalle}", cmap=CMAP_ESTADO))
with v2:
    d_dep = det.groupby("Departamento").size().reset_index(name="Registros")
    mostrar(pie(d_dep, "Departamento", "Registros", f"Departamentos · {paquete_detalle}",
                cmap=CMAP_DEPTO))

# ============================================================
# INFORMACIÓN PENDIENTE (agrupa lo que antes estaba repetido en 4 bloques)
# ============================================================
with st.expander("📝 Información que falta en el Excel para completar el dashboard"):
    st.markdown("""
- **Alineación estratégica:** objetivo estratégico por paquete (Objetivo → Paquete → Intervención → Impacto).
- **Dependencias:** paquete origen, paquete afectado, tipo de dependencia, responsable y fecha límite.
- **Riesgos:** probabilidad, impacto, responsable y fecha de tratamiento.
- **Cronograma:** fecha inicio, fin planificada, fin real y avance planificado/real.
- **Costos:** presupuesto, ejecutado, saldo y desviación por paquete.
- **Recursos:** capacidad requerida vs. disponible por paquete y responsable.

*El dashboard no inventa estos datos; se activarán cuando existan las columnas.*
""")

# ============================================================
# FOOTER
# ============================================================
st.caption(
    f"Descolmatación · {CAMPANA} · Información al {FECHA_CORTE} · "
    "Fuente: EXCEL DS 164 EF.xlsx · Agrupación por paquete normalizado "
    "(ej.: PIURA PQ 2 y cualquier otro registro con PQ 2 se consolidan como PQ 2)."
)

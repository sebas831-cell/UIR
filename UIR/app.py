
import re
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ============================================================
# CONFIGURACIÓN
# ============================================================
st.set_page_config(
    page_title="Dashboard Ejecutivo PMO",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# ESTILO
# ============================================================
st.markdown("""
<style>
.stApp { background:#F3F6F9; }
.block-container { max-width: 1600px; padding: 1rem 2rem 2rem; }

.header {
    background: linear-gradient(135deg,#09243D,#0E4265);
    color:white; padding:22px 28px; border-radius:14px;
    margin-bottom:16px;
}
.header h1 { margin:0; font-size:30px; }
.header p { margin:5px 0 0; opacity:.82; }

.kpi {
    background:white; border:1px solid #E4EAF0; border-radius:12px;
    padding:15px 18px; min-height:105px;
    box-shadow:0 2px 8px rgba(15,23,42,.05);
}
.kpi-label { color:#64748B; font-size:12px; font-weight:600; }
.kpi-value { color:#09243D; font-size:27px; font-weight:800; margin-top:3px; }
.kpi-help { color:#94A3B8; font-size:11px; }

.section {
    color:#09243D; font-size:18px; font-weight:800;
    margin:18px 0 8px;
}
.card {
    background:white; border:1px solid #E4EAF0; border-radius:12px;
    padding:15px; height:100%;
}
.alert-red { background:#FEF2F2; border-left:5px solid #DC2626; padding:12px; border-radius:8px; }
.alert-amber { background:#FFF7ED; border-left:5px solid #F59E0B; padding:12px; border-radius:8px; }
.alert-green { background:#F0FDF4; border-left:5px solid #16A34A; padding:12px; border-radius:8px; }

div[data-testid="stMetric"] {
    background:white; border:1px solid #E4EAF0; padding:12px;
    border-radius:12px;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# CARGA
# ============================================================
BASE = Path(__file__).resolve().parent
EXCEL = BASE / "EXCEL DS 164 EF.xlsx"

@st.cache_data
def cargar_excel():
    data = pd.read_excel(EXCEL)
    data = data.dropna(axis=1, how="all").copy()

    # Normalización de nombres reales del Excel
    ren = {}
    for c in data.columns:
        t = str(c).strip().lower()
        if t == "ben": ren[c] = "Beneficiarios"
        elif t == "ha": ren[c] = "Hectareas"
        elif t == "km": ren[c] = "Km"
    data.rename(columns=ren, inplace=True)

    # Paquete CANÓNICO:
    # "PIURA PQ 2", "LA LIBERTAD PQ 2", etc. -> "PQ 2"
    def normalizar_paquete(v):
        if pd.isna(v) or str(v).strip() == "":
            return "SIN PAQUETE"
        s = str(v).strip().upper()
        m = re.search(r"\bPQ\s*[-_]?\s*(\d+)\b", s)
        if m:
            return f"PQ {m.group(1)}"
        return s

    data["Paquete"] = data["Paquete"].map(normalizar_paquete)

    for c in ["Km", "Beneficiarios", "Hectareas"]:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0)

    data["Estado"] = data["Estado"].fillna("SIN ESTADO").astype(str).str.strip().str.upper()
    return data

if not EXCEL.exists():
    st.error(f"No se encontró el archivo: {EXCEL}")
    st.stop()

df0 = cargar_excel()

# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div class="header">
<h1>📊 Portafolio de Proyectos — Dashboard Ejecutivo PMO</h1>
<p>Vista ejecutiva por paquetes · estado · impacto · riesgos · decisiones</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# FILTROS
# ============================================================
st.markdown('<div class="section">🔎 Filtros del portafolio</div>', unsafe_allow_html=True)
f1, f2, f3, f4, f5 = st.columns([1.1,1.1,1.1,1.2,1.2])

def opciones(col):
    return sorted(df0[col].dropna().astype(str).unique().tolist())

departamentos = f1.multiselect("Departamento", opciones("Departamento"))
provincias = f2.multiselect("Provincia", opciones("Provincia"))
distritos = f3.multiselect("Distrito", opciones("Distrito"))
paquetes = f4.multiselect("Paquete", opciones("Paquete"))
estados = f5.multiselect("Estado", opciones("Estado"))

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

# ============================================================
# KPIs
# ============================================================
total = len(df)
ejecucion = int((df["Estado"].str.contains("EJECUCION", na=False)).sum())
contratacion = int((df["Estado"].str.contains("CONTRATACION", na=False)).sum())
desestimados = int((df["Estado"].str.contains("DESESTIMADA", na=False)).sum())
benef = df["Beneficiarios"].sum()
ha = df["Hectareas"].sum()
km = df["Km"].sum()
paquetes_activos = df.loc[df["Paquete"].str.match(r"^PQ \d+$"), "Paquete"].nunique()

# Atención: no inventa riesgos; identifica estados que requieren seguimiento
atencion_mask = (
    df["Estado"].str.contains("CONTRATACION|DESESTIMADA|PENDIENTE|RIESGO|RETRAS|OBSERV", regex=True, na=False)
)
atencion = int(atencion_mask.sum())

st.markdown('<div class="section">📌 Indicadores ejecutivos</div>', unsafe_allow_html=True)
k = st.columns(7)

def kpi(c, label, value, help_text):
    c.markdown(f"""
    <div class="kpi">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-help">{help_text}</div>
    </div>
    """, unsafe_allow_html=True)

kpi(k[0],"PAQUETES",f"{paquetes_activos}","PQ únicos del portafolio")
kpi(k[1],"REGISTROS",f"{total:,}","Intervenciones filtradas")
kpi(k[2],"EN EJECUCIÓN",f"{ejecucion:,}","Estado actual")
kpi(k[3],"EN CONTRATACIÓN",f"{contratacion:,}","Requieren seguimiento")
kpi(k[4],"BENEFICIARIOS",f"{benef:,.0f}","Impacto acumulado")
kpi(k[5],"HECTÁREAS",f"{ha:,.2f}","Área beneficiada")
kpi(k[6],"KM",f"{km:,.2f}","Intervención acumulada")

# ============================================================
# PAQUETES — BLOQUE PRINCIPAL
# ============================================================
st.markdown('<div class="section">📦 Portafolio por paquete</div>', unsafe_allow_html=True)

pkg = (
    df.groupby("Paquete", dropna=False)
      .agg(
          Intervenciones=("Paquete","size"),
          Beneficiarios=("Beneficiarios","sum"),
          Hectareas=("Hectareas","sum"),
          Km=("Km","sum"),
          Departamentos=("Departamento","nunique"),
          Provincias=("Provincia","nunique")
      )
      .reset_index()
)

pkg["Orden"] = pkg["Paquete"].str.extract(r"(\d+)").astype(float)
pkg.loc[pkg["Paquete"]=="DESESTIMADA","Orden"] = 999
pkg = pkg.sort_values(["Orden","Paquete"]).drop(columns="Orden")

c1, c2 = st.columns([1.55,1])

with c1:
    fig = px.bar(
        pkg,
        x="Paquete",
        y="Intervenciones",
        text="Intervenciones",
        title="Intervenciones por paquete"
    )
    fig.update_layout(height=310, margin=dict(l=10,r=10,t=50,b=10),
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    fig = px.bar(
        pkg,
        x="Paquete",
        y="Beneficiarios",
        text="Beneficiarios",
        title="Beneficiarios por paquete"
    )
    fig.update_layout(height=310, margin=dict(l=10,r=10,t=50,b=10),
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# DISTRIBUCIÓN CIRCULAR: DEPARTAMENTOS Y PROVINCIAS POR PAQUETE
# ============================================================
st.markdown(
    '<div class="section">🎯 Distribución Territorial y por Paquetes</div>',
    unsafe_allow_html=True,
)

c_circ1, c_circ2 = st.columns(2)

with c_circ1:
  st.markdown('**Intervenciones por Departamento**')
  dep_data = (
      df.groupby('Departamento')
      .size()
      .reset_index(name='Intervenciones')
  )
  fig_dep_pie = px.pie(
      dep_data,
      names='Departamento',
      values='Intervenciones',
      hole=0.4,
      title='Participación por Departamento',
  )
  fig_dep_pie.update_layout(
      height=350, margin=dict(l=10, r=10, t=50, b=10), paper_bgcolor='white'
  )
  st.plotly_chart(fig_dep_pie, use_container_width=True)

with c_circ2:
  st.markdown('**Provincias y Paquetes por Departamento**')

  # Selector exclusivo para este gráfico dinámico
  deptos_disponibles = sorted(df['Departamento'].dropna().unique())
  if deptos_disponibles:
    dept_elegido = st.selectbox(
        'Seleccione un Departamento:',
        deptos_disponibles,
        key='select_dept_circulo',
    )

    # Filtrar datos por el departamento seleccionado
    df_dept_filtered = df[df['Departamento'] == dept_elegido]

    # Agrupar por Provincia (o Paquete según prefieras visualizar)
    prov_data = (
        df_dept_filtered.groupby('Provincia')
        .size()
        .reset_index(name='Intervenciones')
    )

    if not prov_data.empty:
      fig_prov_pie = px.pie(
          prov_data,
          names='Provincia',
          values='Intervenciones',
          hole=0.4,
          title=f'Provincias en {dept_elegido}',
      )
      fig_prov_pie.update_layout(
          height=312, margin=dict(l=10, r=10, t=50, b=10), paper_bgcolor='white'
      )
      st.plotly_chart(fig_prov_pie, use_container_width=True)
    else:
      st.warning('No hay registros para este departamento con los filtros actual.')
  else:
    st.info('No hay departamentos disponibles.')

# ============================================================
# MÉTRICAS TERRITORIALES (Km, Beneficiarios y Hectáreas)
# ============================================================
st.markdown('<div class="section">🗺️ Análisis Territorial por Indicadores (Km, Beneficiarios y Hectáreas)</div>', unsafe_allow_html=True)

# Selector global para elegir qué indicador analizar en los gráficos circulares
metrica_seleccionada = st.selectbox(
    "Selecciona el indicador a evaluar:",
    options=["Beneficiarios", "Hectareas", "Km"],
    key="select_metrica_territorial"
)

col_met1, col_met2 = st.columns(2)

with col_met1:
    st.markdown(f"**{metrica_seleccionada} por Departamento**")
    # Agrupar por departamento sumando la métrica elegida
    dep_metric_data = df.groupby("Departamento")[metrica_seleccionada].sum().reset_index()
    # Filtrar valores en 0 para evitar gráficos vacíos o confusos
    dep_metric_data = dep_metric_data[dep_metric_data[metrica_seleccionada] > 0]
    
    if not dep_metric_data.empty:
        fig_dep_metric = px.pie(
            dep_metric_data,
            names="Departamento",
            values=metrica_seleccionada,
            hole=0.4,
            title=f"Distribución de {metrica_seleccionada} por Departamento"
        )
        fig_dep_metric.update_layout(height=350, margin=dict(l=10,r=10,t=50,b=10), paper_bgcolor="white")
        st.plotly_chart(fig_dep_metric, use_container_width=True)
    else:
        st.warning(f"No hay datos acumulados para {metrica_seleccionada} en los departamentos seleccionados.")

with col_met2:
    st.markdown(f"**{metrica_seleccionada} por Provincia (según Departamento)**")
    
    deptos_metric_disp = sorted(df["Departamento"].dropna().unique())
    if deptos_metric_disp:
        # Selector exclusivo para este gráfico de provincias
        dept_elegido_metric = st.selectbox(
            "Seleccione un Departamento para detalle provincial:",
            deptos_metric_disp,
            key="select_dept_metric_prov"
        )
        
        df_dept_metric_filtered = df[df["Departamento"] == dept_elegido_metric]
        prov_metric_data = df_dept_metric_filtered.groupby("Provincia")[metrica_seleccionada].sum().reset_index()
        prov_metric_data = prov_metric_data[prov_metric_data[metrica_seleccionada] > 0]
        
        if not prov_metric_data.empty:
            fig_prov_metric = px.pie(
                prov_metric_data,
                names="Provincia",
                values=metrica_seleccionada,
                hole=0.4,
                title=f"{metrica_seleccionada} en Provincias de {dept_elegido_metric}"
            )
            fig_prov_metric.update_layout(height=312, margin=dict(l=10,r=10,t=50,b=10), paper_bgcolor="white")
            st.plotly_chart(fig_prov_metric, use_container_width=True)
        else:
            st.warning(f"No se registran valores de {metrica_seleccionada} para las provincias de este departamento.")
    else:
        st.info("No hay departamentos disponibles para desglosar.")

# ============================================================
# ESTADO + IMPACTO
# ============================================================
st.markdown('<div class="section">📈 Estado e impacto</div>', unsafe_allow_html=True)
a,b = st.columns(2)

with a:
    estado = df["Estado"].value_counts().reset_index()
    estado.columns = ["Estado","Cantidad"]
    fig = px.bar(estado, y="Estado", x="Cantidad", orientation="h",
                 text="Cantidad", title="Estado del portafolio")
    fig.update_layout(height=330, margin=dict(l=10,r=10,t=50,b=10),
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

with b:
    impacto = pd.DataFrame({
        "Indicador":["Beneficiarios","Hectáreas","Km"],
        "Valor":[benef,ha,km]
    })
    fig = px.bar(impacto, x="Indicador", y="Valor", text="Valor",
                 title="Impacto acumulado")
    fig.update_layout(height=330, margin=dict(l=10,r=10,t=50,b=10),
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# ALERTAS / DECISIONES
# ============================================================
st.markdown('<div class="section">🚨 Atención y decisiones</div>', unsafe_allow_html=True)
r1,r2,r3 = st.columns(3)

with r1:
    st.markdown(f"""
    <div class="alert-red">
    <b>ATENCIÓN</b><br><br>
    {atencion:,} registros presentan estados que requieren
    seguimiento según la información disponible.
    </div>
    """, unsafe_allow_html=True)

with r2:
    st.markdown(f"""
    <div class="alert-amber">
    <b>PMO</b><br><br>
    Priorizar la revisión de los paquetes con mayor volumen
    de intervenciones y estados pendientes/contratación.
    </div>
    """, unsafe_allow_html=True)

with r3:
    st.markdown("""
    <div class="alert-green">
    <b>DECISIÓN</b><br><br>
    Validar responsables, fechas, presupuesto, recursos,
    riesgos y dependencias antes de convertirlos en KPIs ejecutivos.
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# DISTRIBUCIÓN TERRITORIAL
# ============================================================
st.markdown('<div class="section">🌎 Distribución territorial</div>', unsafe_allow_html=True)
t1,t2 = st.columns(2)

with t1:
    dep = df["Departamento"].value_counts().reset_index()
    dep.columns = ["Departamento","Intervenciones"]
    fig = px.bar(dep, x="Departamento", y="Intervenciones",
                 text="Intervenciones", title="Intervenciones por departamento")
    fig.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
                      margin=dict(l=10,r=10,t=50,b=10))
    st.plotly_chart(fig, use_container_width=True)

with t2:
    # Participación de cada paquete en beneficiarios
    fig = px.pie(pkg, names="Paquete", values="Beneficiarios",
                 title="Participación de beneficiarios por paquete", hole=.48)
    fig.update_layout(height=300, margin=dict(l=10,r=10,t=50,b=10))
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# ALINEACIÓN ESTRATÉGICA
# ============================================================
st.markdown('<div class="section">🎯 Alineación estratégica</div>', unsafe_allow_html=True)
st.info(
    "El Excel actual no contiene una columna de objetivo estratégico. "
    "Por ello el dashboard no asigna objetivos de forma ficticia. "
    "Cuando se agregue esa columna, podrá relacionarse directamente "
    "Objetivo → Paquete → Intervención → Impacto."
)

# ============================================================
# RIESGOS Y DEPENDENCIAS
# ============================================================
st.markdown('<div class="section">⚠️ Riesgos y dependencias</div>', unsafe_allow_html=True)
rr1,rr2 = st.columns(2)

with rr1:
    at_df = df[atencion_mask].groupby(["Paquete","Estado"]).size().reset_index(name="Registros")
    if len(at_df):
        fig = px.bar(at_df, x="Paquete", y="Registros", color="Estado",
                     barmode="stack", title="Registros que requieren seguimiento por paquete")
        fig.update_layout(height=310, margin=dict(l=10,r=10,t=50,b=10),
                          plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("No se detectaron estados de atención con las reglas actuales.")

with rr2:
    st.markdown("""
    <div class="card">
    <b>Dependencias</b><br><br>
    El archivo no contiene todavía una matriz explícita de dependencias entre
    proyectos o paquetes. No se generan dependencias ficticias.
    <br><br>
    <b>Para habilitar esta sección:</b><br>
    Paquete origen · Paquete afectado · Tipo de dependencia · Responsable · Fecha límite.
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# DETALLE OPERATIVO POR PAQUETE
# ============================================================
st.markdown('<div class="section">🔍 Detalle operativo por paquete</div>', unsafe_allow_html=True)

paquete_detalle = st.selectbox(
    "Selecciona un paquete",
    sorted(df["Paquete"].unique()),
    index=0 if len(df) else None
)

if paquete_detalle:
    det = df[df["Paquete"] == paquete_detalle].copy()

    q1,q2,q3,q4 = st.columns(4)
    q1.metric("Intervenciones", f"{len(det):,}")
    q2.metric("Beneficiarios", f"{det['Beneficiarios'].sum():,.0f}")
    q3.metric("Ha", f"{det['Hectareas'].sum():,.2f}")
    q4.metric("Km", f"{det['Km'].sum():,.2f}")

    st.dataframe(
        det[[
            "Departamento","Provincia","Distrito","Sector",
            "Paquete","Km","Beneficiarios","Hectareas","Estado"
        ]],
        use_container_width=True,
        hide_index=True,
        height=350
    )

# ============================================================
# DECISIONES / PRÓXIMOS PASOS
# ============================================================
st.markdown('<div class="section">🧭 Decisiones y próximos pasos para PMO</div>', unsafe_allow_html=True)

st.markdown("""
<div class="card">
<b>1. Priorizar</b> — Revisar primero los paquetes con mayor número de intervenciones
en estados de contratación, pendientes o desestimados.<br><br>

<b>2. Validar riesgos</b> — Incorporar probabilidad, impacto, responsable y fecha
de tratamiento para que el semáforo sea ejecutivo y medible.<br><br>

<b>3. Incorporar cronograma</b> — Fecha inicio, fecha fin planificada, fecha fin real
y avance planificado/real para calcular retrasos.<br><br>

<b>4. Incorporar costos</b> — Presupuesto, ejecutado, saldo y desviación por paquete.<br><br>

<b>5. Incorporar recursos</b> — Capacidad requerida vs. disponible por paquete y responsable.<br><br>

<b>6. Alineación estratégica</b> — Registrar el objetivo estratégico asociado a cada paquete
para responder qué proyectos contribuyen a cada objetivo.
</div>
""", unsafe_allow_html=True)

# ============================================================
# FOOTER
# ============================================================
st.caption(
    "Fuente: EXCEL DS 164 EF.xlsx · Agrupación ejecutiva por paquete normalizado. "
    "Ejemplo: PIURA PQ 2 y cualquier otro registro con PQ 2 se consolidan como PQ 2."
)

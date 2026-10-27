import pandas as pd
import io
import sqlite3
import re
import os

DB_PATH = "eficiencia_historia.db"

CARPETA_SAP = r"C:\Users\suarezr\Desktop\50.001"
CARPETA_HPHI = r"C:\Users\suarezr\Desktop\HPHI"
CARPETA_910_920 = r"C:\Users\suarezr\Desktop\DENCRE"

def inicializar_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_repuestos_mensual (
            ejercicio_inicio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            valor REAL NOT NULL,
            PRIMARY KEY (ejercicio_inicio, mes)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historia_diaria_planta (
            fecha TEXT PRIMARY KEY,
            horas_programadas REAL,
            horas_producidas_total REAL,
            horas_producidas_pt REAL,
            horas_programadas_pt REAL,
            horas_producidas_se REAL,
            horas_programadas_se REAL,
            eficiencia_global_porcentaje REAL,
            eficiencia_pt_porcentaje REAL,
            eficiencia_se_porcentaje REAL,
            kilos_totales_pt REAL,
            unidades_totales_pt REAL,
            unidades_totales_se REAL,
            total_filas_sap INTEGER
        )
    ''')
    
    cursor.execute("PRAGMA table_info(historia_diaria_planta)")
    cols = [col[1] for col in cursor.fetchall()]
    if 'horas_programadas_pt' not in cols:
        cursor.execute("ALTER TABLE historia_diaria_planta ADD COLUMN horas_programadas_pt REAL DEFAULT 0")
    if 'horas_programadas_se' not in cols:
        cursor.execute("ALTER TABLE historia_diaria_planta ADD COLUMN horas_programadas_se REAL DEFAULT 0")

    try:
        cursor.execute("SELECT ritmo_prog FROM historia_detalle_filas LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS historia_detalle_filas")
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historia_detalle_filas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            puesto_trabajo INTEGER,
            turno TEXT,
            codigo_maquinista TEXT,
            orden_fabricacion TEXT,
            producto TEXT,
            ritmo_max REAL,
            ritmo_prog REAL,
            peso_unitario REAL,
            unidades_producidas REAL,
            unidades_cod_910 REAL,
            unidades_cod_920 REAL,
            peso_producido REAL,
            kg_programado REAL,
            hs_programadas REAL,
            hs_productivas REAL,
            eficiencia REAL,
            tipo_producto TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metas_maquina (
            puesto_trabajo INTEGER PRIMARY KEY,
            objetivo_anual REAL DEFAULT 0.0,
            resultado_anterior REAL DEFAULT 0.0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maquinas_sap (
            puesto_trabajo INTEGER PRIMARY KEY
        )
    ''')
    cursor.execute("""
        INSERT OR IGNORE INTO maquinas_sap (puesto_trabajo)
        SELECT DISTINCT puesto_trabajo
        FROM historia_detalle_filas
        WHERE puesto_trabajo IS NOT NULL AND puesto_trabajo > 0
    """)
    cursor.executemany(
        "INSERT OR IGNORE INTO maquinas_sap (puesto_trabajo) VALUES (?)",
        [(80,), (708,)]
    )
    cursor.execute("DELETE FROM maquinas_sap WHERE puesto_trabajo = 20")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eficiencia_bi_diaria (
            fecha TEXT NOT NULL,
            puesto_trabajo INTEGER NOT NULL,
            horas_programadas REAL NOT NULL,
            horas_productivas REAL NOT NULL,
            PRIMARY KEY (fecha, puesto_trabajo)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metas_planta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            objetivo_anual REAL NOT NULL DEFAULT 0.0,
            resultado_anterior REAL NOT NULL DEFAULT 0.0,
            objetivo_mes_kg REAL NOT NULL DEFAULT 0.0
        )
    ''')
    cursor.execute("PRAGMA table_info(metas_planta)")
    columnas_metas_planta = [columna[1] for columna in cursor.fetchall()]
    if "objetivo_mes_kg" not in columnas_metas_planta:
        cursor.execute(
            "ALTER TABLE metas_planta ADD COLUMN objetivo_mes_kg REAL NOT NULL DEFAULT 0.0"
        )
    cursor.execute("""
        INSERT OR IGNORE INTO metas_planta (
            id, objetivo_anual, resultado_anterior, objetivo_mes_kg
        ) VALUES (1, 0.0, 0.0, 0.0)
    """)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eficiencia_maquina_708_diaria (
            fecha TEXT PRIMARY KEY,
            horas_codigo_902 REAL NOT NULL,
            horas_totales REAL NOT NULL,
            eficiencia_porcentaje REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eventos_hphi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            puesto_trabajo INTEGER NOT NULL,
            orden TEXT NOT NULL DEFAULT '',
            material TEXT NOT NULL DEFAULT '',
            turno TEXT NOT NULL DEFAULT '',
            concepto INTEGER NOT NULL,
            duracion_horas REAL NOT NULL DEFAULT 0,
            descripcion TEXT NOT NULL DEFAULT ''
        )
    ''')
    columnas_eventos_hphi = {
        fila[1] for fila in cursor.execute("PRAGMA table_info(eventos_hphi)").fetchall()
    }
    if "descripcion" not in columnas_eventos_hphi:
        cursor.execute(
            "ALTER TABLE eventos_hphi ADD COLUMN descripcion TEXT NOT NULL DEFAULT ''"
        )
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_eventos_hphi_fecha_puesto
        ON eventos_hphi (fecha, puesto_trabajo)
    ''')
    conn.commit()
    conn.close()

def parsear_numero_sap(val):
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace('.', '').replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def convertir_a_horas_float(val):
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        parts = val.strip().split(':')
        if len(parts) == 3:
            try:
                return float(parts[0]) + float(parts[1])/60.0 + float(parts[2])/3600.0
            except ValueError:
                return 0.0
    if hasattr(val, 'hour'):
        return float(val.hour) + float(val.minute)/60.0 + float(val.second)/3600.0
    return 0.0

def normalizar_codigo_hphi(valor, quitar_ceros_iniciales=False):
    if pd.isna(valor) or valor is None:
        return ""

    codigo = str(valor).strip()
    if codigo.lower() in ("", "nan", "none"):
        return ""
    if codigo.endswith(".0"):
        codigo = codigo[:-2]
    return codigo.lstrip("0") if quitar_ceros_iniciales else codigo

def calcular_eficiencia_maquina_708(df_hphi):
    if df_hphi is None or df_hphi.empty:
        return []

    df = df_hphi.copy()
    df.columns = df.columns.astype(str).str.strip()

    def seleccionar_columna(predicado, indice_fallback):
        coincidencias = [col for col in df.columns if predicado(col.lower())]
        if coincidencias:
            return coincidencias[0]
        if len(df.columns) > indice_fallback:
            return df.columns[indice_fallback]
        raise ValueError("El archivo HPHI no contiene las columnas requeridas para la máquina 708.")

    col_fecha = seleccionar_columna(lambda nombre: "fecha" in nombre, 0)
    col_puesto = seleccionar_columna(
        lambda nombre: "puesto" in nombre or "máquina" in nombre or "maquina" in nombre,
        1
    )
    col_codigo = next((col for col in df.columns if "concepto" in col.lower()), None)
    if col_codigo is None:
        col_codigo = next(
            (
                col for col in df.columns
                if any(palabra in col.lower() for palabra in ("código", "codigo", "parada", "evento"))
                and "turno" not in col.lower()
            ),
            df.columns[4] if len(df.columns) > 4 else None
        )
    if col_codigo is None:
        raise ValueError("El archivo HPHI no contiene la columna de concepto requerida para la máquina 708.")
    col_duracion = seleccionar_columna(
        lambda nombre: "duración" in nombre or "duracion" in nombre,
        7
    )

    df["Fecha_708"] = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")
    df["Puesto_708"] = pd.to_numeric(df[col_puesto], errors="coerce")
    df["Codigo_708"] = df[col_codigo].apply(parsear_numero_sap)
    df["Duracion_708"] = df[col_duracion].apply(convertir_a_horas_float)
    df = df[
        (df["Puesto_708"] == 708)
        & df["Fecha_708"].notna()
        & (df["Fecha_708"] != "")
    ].copy()

    if df.empty:
        return []

    resultados = []
    for fecha, grupo in df.groupby("Fecha_708"):
        horas_totales = float(grupo["Duracion_708"].sum())
        horas_codigo_902 = float(grupo.loc[grupo["Codigo_708"] == 902, "Duracion_708"].sum())
        eficiencia = round(horas_codigo_902 / horas_totales * 100.0, 2) if horas_totales > 0 else None
        resultados.append((fecha, horas_codigo_902, horas_totales, eficiencia))

    return resultados

def limpiar_y_calcular_sap(archivo_sap_bytes=None, 
                            df_hphi_consolidado=None,
                            df_910_920_consolidado=None,
                            archivo_hphi_bytes=None,
                            archivo_910_920_bytes=None,
                            nombre_archivo="",
                            archivo_ritmos_path="Nueva Base Ritmos 2223 V03.xlsx"):
    try:
        inicializar_db()

        if not archivo_sap_bytes:
            return {"estado": "error", "mensaje": "Se requiere el archivo principal de SAP."}

        df_sap = pd.read_excel(io.BytesIO(archivo_sap_bytes), engine='openpyxl')
        df_sap.columns = df_sap.columns.astype(str).str.strip()
        df_sap = df_sap.dropna(how='all')

        cols_ffill = [c for c in df_sap.columns if any(k in c.lower() for k in ['f.cont', 'puesto', 'turno', 'código maq', 'nombre maq'])]
        df_sap[cols_ffill] = df_sap[cols_ffill].ffill()

        c_fecha = [c for c in df_sap.columns if 'f.cont' in c.lower()][0] if any('f.cont' in c.lower() for c in df_sap.columns) else df_sap.columns[2]
        c_puesto = [c for c in df_sap.columns if 'puesto' in c.lower()][0] if any('puesto' in c.lower() for c in df_sap.columns) else df_sap.columns[3]
        c_turno = [c for c in df_sap.columns if 'turno' in c.lower()][0] if any('turno' in c.lower() for c in df_sap.columns) else df_sap.columns[4]
        c_legajo = [c for c in df_sap.columns if 'código maq' in c.lower() or 'legajo' in c.lower()][0] if any('código maq' in c.lower() for c in df_sap.columns) else df_sap.columns[5]
        c_orden = [c for c in df_sap.columns if 'orden' in c.lower() or 'fabric' in c.lower()][0] if any('orden' in c.lower() for c in df_sap.columns) else df_sap.columns[7]
        c_prod = [c for c in df_sap.columns if 'producto' in c.lower()][0] if any('producto' in c.lower() for c in df_sap.columns) else df_sap.columns[8]
        c_peso_u = [c for c in df_sap.columns if 'peso un' in c.lower() or 'unitario' in c.lower()][0] if any('unitario' in c.lower() for c in df_sap.columns) else df_sap.columns[10]
        c_unid = [c for c in df_sap.columns if 'unidades' in c.lower()][0] if any('unidades' in c.lower() for c in df_sap.columns) else df_sap.columns[11]

        c_910 = [c for c in df_sap.columns if '910' in c]
        c_920 = [c for c in df_sap.columns if '920' in c]
        col_910 = c_910[0] if c_910 else None
        col_920 = c_920[0] if c_920 else None

        df_sap['Fecha_Clean'] = pd.to_datetime(df_sap[c_fecha], errors='coerce', dayfirst=True).dt.strftime('%Y-%m-%d')
        df_sap = df_sap.dropna(subset=[c_prod, 'Fecha_Clean']).copy()

        df_sap['Material_Clean'] = df_sap[c_prod].astype(str).str.replace('.0', '', regex=False).str.strip().str.lstrip('0')
        df_sap['Tipo_Producto'] = df_sap['Material_Clean'].apply(lambda x: 'PT' if len(x) == 6 else ('SE' if len(x) == 9 else 'OTRO'))
        df_sap['Puesto_Clean'] = pd.to_numeric(df_sap[c_puesto], errors='coerce').fillna(0).astype(int)
        df_sap['Turno_Clean'] = df_sap[c_turno].astype(str).str.strip()
        df_sap['Legajo_Clean'] = df_sap[c_legajo].astype(str).str.replace('.0', '', regex=False).str.strip()
        df_sap['Orden_Clean'] = df_sap[c_orden].astype(str).str.replace('.0', '', regex=False).str.strip()

        df_sap['Peso_Unitario'] = df_sap[c_peso_u].apply(parsear_numero_sap)
        df_sap['Unidades_Reales'] = df_sap[c_unid].apply(parsear_numero_sap)
        df_sap['Unid_910'] = df_sap[col_910].apply(parsear_numero_sap) if col_910 else 0.0
        df_sap['Unid_920'] = df_sap[col_920].apply(parsear_numero_sap) if col_920 else 0.0

        mapa_910 = {}
        mapa_920 = {}
        
        if df_910_920_consolidado is None and archivo_910_920_bytes:
            try:
                df_910_920_consolidado = pd.read_excel(io.BytesIO(archivo_910_920_bytes))
            except Exception:
                pass

        if df_910_920_consolidado is not None and not df_910_920_consolidado.empty:
            try:
                df_extra = df_910_920_consolidado.copy()
                df_extra.columns = df_extra.columns.astype(str).str.strip()
                col_f_ex = [c for c in df_extra.columns if 'fecha' in c.lower()][0]
                col_m_ex = [c for c in df_extra.columns if 'puesto' in c.lower() or 'máquina' in c.lower() or 'maquina' in c.lower()][0]
                col_o_ex = [c for c in df_extra.columns if 'orden' in c.lower()][0]
                col_c_ex = [c for c in df_extra.columns if 'concepto' in c.lower() or 'id' in c.lower()][0]
                col_p_ex = [c for c in df_extra.columns if 'material' in c.lower() or 'producto' in c.lower()][0]
                col_q_ex = [c for c in df_extra.columns if 'cantidad' in c.lower()][0]

                df_extra['Fecha_Clean'] = pd.to_datetime(df_extra[col_f_ex], errors='coerce', dayfirst=True).dt.strftime('%Y-%m-%d')
                df_extra['Puesto_Clean'] = pd.to_numeric(df_extra[col_m_ex], errors='coerce').fillna(0).astype(int)
                df_extra['Orden_Clean'] = df_extra[col_o_ex].astype(str).str.replace('.0', '', regex=False).str.strip()
                df_extra['Material_Clean'] = df_extra[col_p_ex].astype(str).str.replace('.0', '', regex=False).str.strip().str.lstrip('0')
                df_extra['Concepto'] = df_extra[col_c_ex].astype(str).str.strip()
                df_extra['Cantidad_Clean'] = df_extra[col_q_ex].apply(parsear_numero_sap)

                df_910 = df_extra[df_extra['Concepto'] == '910']
                df_920 = df_extra[df_extra['Concepto'] == '920']

                mapa_910 = df_910.groupby(['Fecha_Clean', 'Puesto_Clean', 'Orden_Clean', 'Material_Clean'])['Cantidad_Clean'].sum().to_dict()
                mapa_920 = df_920.groupby(['Fecha_Clean', 'Puesto_Clean', 'Orden_Clean', 'Material_Clean'])['Cantidad_Clean'].sum().to_dict()
            except Exception as e_ex:
                print(f"Advertencia al procesar DENCRE: {e_ex}")

        df_ritmos = pd.read_excel(archivo_ritmos_path, header=0)
        col_puesto_r = df_ritmos.columns[1]
        col_mat_r = df_ritmos.columns[2]
        col_ritmo_max_r = df_ritmos.columns[5]
        col_ritmo_prog_r = df_ritmos.columns[6] if len(df_ritmos.columns) > 6 else df_ritmos.columns[5]

        df_ritmos['Material_Clean'] = df_ritmos[col_mat_r].astype(str).str.replace('.0', '', regex=False).str.strip().str.lstrip('0')
        df_ritmos['Puesto_Clean'] = pd.to_numeric(df_ritmos[col_puesto_r], errors='coerce').fillna(0).astype(int)
        df_ritmos['Ritmo_Max'] = df_ritmos[col_ritmo_max_r].apply(parsear_numero_sap)
        df_ritmos['Ritmo_Prog'] = df_ritmos[col_ritmo_prog_r].apply(parsear_numero_sap)

        df_ritmos_clean = df_ritmos[['Material_Clean', 'Puesto_Clean', 'Ritmo_Max', 'Ritmo_Prog']].drop_duplicates()
        df_final = pd.merge(df_sap, df_ritmos_clean, on=['Material_Clean', 'Puesto_Clean'], how='left')

        df_ritmos_backup = df_ritmos.groupby('Material_Clean').agg({'Ritmo_Max': 'max', 'Ritmo_Prog': 'max'}).reset_index()
        df_final = pd.merge(df_final, df_ritmos_backup, on='Material_Clean', how='left', suffixes=('', '_backup'))

        df_final['Ritmo_Final'] = df_final['Ritmo_Max'].fillna(df_final['Ritmo_Max_backup']).fillna(0)
        df_final['Ritmo_Prog_Final'] = df_final['Ritmo_Prog'].fillna(df_final['Ritmo_Prog_backup']).fillna(0)
        ritmos_por_puesto_producto = (
            df_ritmos.groupby(['Puesto_Clean', 'Material_Clean'])
            .agg({'Ritmo_Max': 'max', 'Ritmo_Prog': 'max'})
            .to_dict('index')
        )
        ritmos_por_producto = (
            df_ritmos_backup.set_index('Material_Clean')[['Ritmo_Max', 'Ritmo_Prog']]
            .to_dict('index')
        )

        maquinas_excluidas = [16, 18, 44, 80, 91, 108, 117, 118, 708]
        df_global = df_final[~df_final['Puesto_Clean'].isin(maquinas_excluidas)].copy()

        df_hphi_global = pd.DataFrame()
        df_hphi_eventos = pd.DataFrame()
        eficiencia_708_por_fecha = []
        if df_hphi_consolidado is None and archivo_hphi_bytes:
            try:
                df_hphi_consolidado = pd.read_excel(io.BytesIO(archivo_hphi_bytes))
            except Exception:
                pass

        if df_hphi_consolidado is not None and not df_hphi_consolidado.empty:
            eficiencia_708_por_fecha = calcular_eficiencia_maquina_708(df_hphi_consolidado)
            try:
                df_hphi_raw = df_hphi_consolidado.copy()
                df_hphi_raw.columns = df_hphi_raw.columns.astype(str).str.strip()
                col_f_h = [c for c in df_hphi_raw.columns if 'fecha' in c.lower()][0]
                col_maq_h = [c for c in df_hphi_raw.columns if 'puesto' in c.lower() or 'máquina' in c.lower() or 'maquina' in c.lower()][0]
                col_tur_h = [c for c in df_hphi_raw.columns if 'turno' in c.lower()][0]
                col_dur_h = [c for c in df_hphi_raw.columns if 'duración' in c.lower() or 'duracion' in c.lower()][0]
                col_orden_h = next((c for c in df_hphi_raw.columns if 'orden' in c.lower()), None)
                col_producto_h = next(
                    (
                        c for c in df_hphi_raw.columns
                        if (
                            'producto' in c.lower() or 'material' in c.lower()
                        )
                        and 'descrip' not in c.lower()
                    ),
                    None
                )

                df_hphi_raw['Fecha_Clean'] = pd.to_datetime(df_hphi_raw[col_f_h], errors='coerce', dayfirst=True).dt.strftime('%Y-%m-%d')
                df_hphi_raw['Puesto_Clean'] = pd.to_numeric(df_hphi_raw[col_maq_h], errors='coerce').fillna(0).astype(int)
                df_hphi_raw['Turno_Clean'] = df_hphi_raw[col_tur_h].astype(str).str.strip()
                df_hphi_raw['Duracion_Hs'] = df_hphi_raw[col_dur_h].apply(convertir_a_horas_float)
                df_hphi_raw['Orden_HPHI'] = (
                    df_hphi_raw[col_orden_h].apply(normalizar_codigo_hphi)
                    if col_orden_h
                    else ''
                )
                df_hphi_raw['Producto_HPHI'] = (
                    df_hphi_raw[col_producto_h].apply(
                        lambda valor: normalizar_codigo_hphi(valor, quitar_ceros_iniciales=True)
                    )
                    if col_producto_h
                    else ''
                )
                col_concepto_h = next(
                    (c for c in df_hphi_raw.columns if 'concepto' in c.lower()),
                    None
                )
                if col_concepto_h:
                    df_hphi_raw['Concepto_HPHI'] = (
                        pd.to_numeric(df_hphi_raw[col_concepto_h], errors='coerce')
                        .fillna(0)
                        .astype(int)
                    )
                    col_descripcion_h = next(
                        (c for c in df_hphi_raw.columns if 'descrip' in c.lower()),
                        None
                    )
                    df_hphi_raw['Descripcion_HPHI'] = (
                        df_hphi_raw[col_descripcion_h].fillna('').astype(str).str.strip()
                        if col_descripcion_h
                        else ''
                    )
                    df_hphi_eventos = df_hphi_raw[[
                        'Fecha_Clean',
                        'Puesto_Clean',
                        'Orden_HPHI',
                        'Producto_HPHI',
                        'Turno_Clean',
                        'Concepto_HPHI',
                        'Duracion_Hs',
                        'Descripcion_HPHI'
                    ]].copy()

                df_hphi_global = df_hphi_raw[df_hphi_raw['Puesto_Clean'] != 20].copy()
            except Exception as e_hphi:
                print(f"Advertencia al procesar HPHI: {e_hphi}")

        fechas_procesadas = sorted(list(df_final['Fecha_Clean'].unique()))
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if not df_hphi_eventos.empty:
            df_hphi_eventos = df_hphi_eventos[
                df_hphi_eventos['Fecha_Clean'].notna()
                & (df_hphi_eventos['Fecha_Clean'] != '')
                & (df_hphi_eventos['Puesto_Clean'] > 0)
            ]
            fechas_hphi = df_hphi_eventos['Fecha_Clean'].unique().tolist()
            cursor.executemany(
                "DELETE FROM eventos_hphi WHERE fecha = ?",
                [(fecha,) for fecha in fechas_hphi]
            )
            cursor.executemany("""
                INSERT INTO eventos_hphi (
                    fecha, puesto_trabajo, orden, material, turno, concepto, duracion_horas,
                    descripcion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                (
                    row.Fecha_Clean,
                    int(row.Puesto_Clean),
                    str(row.Orden_HPHI),
                    str(row.Producto_HPHI),
                    str(row.Turno_Clean),
                    int(row.Concepto_HPHI),
                    float(row.Duracion_Hs),
                    str(row.Descripcion_HPHI)
                )
                for row in df_hphi_eventos.itertuples(index=False)
            ))

        puestos_sap = sorted(
            int(puesto)
            for puesto in df_sap['Puesto_Clean'].dropna().unique()
            if int(puesto) > 0 and int(puesto) != 20
        )
        cursor.executemany(
            "INSERT OR IGNORE INTO maquinas_sap (puesto_trabajo) VALUES (?)",
            [(puesto,) for puesto in puestos_sap]
        )

        for fecha, horas_902, horas_totales, eficiencia in eficiencia_708_por_fecha:
            cursor.execute("""
                INSERT INTO eficiencia_maquina_708_diaria (
                    fecha, horas_codigo_902, horas_totales, eficiencia_porcentaje
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(fecha) DO UPDATE SET
                    horas_codigo_902 = excluded.horas_codigo_902,
                    horas_totales = excluded.horas_totales,
                    eficiencia_porcentaje = excluded.eficiencia_porcentaje
            """, (fecha, horas_902, horas_totales, eficiencia))

        cursor.execute("""
            SELECT producto, peso_unitario
            FROM historia_detalle_filas
            WHERE peso_unitario > 0
            ORDER BY fecha DESC
        """)
        pesos_historicos_por_producto = {}
        for producto, peso_unitario in cursor.fetchall():
            pesos_historicos_por_producto.setdefault(str(producto), float(peso_unitario))

        for fecha_str in fechas_procesadas:
            df_dia = df_final[df_final['Fecha_Clean'] == fecha_str].copy()
            df_dia_oee = df_global[df_global['Fecha_Clean'] == fecha_str].copy()
            
            mapa_horas_hphi = {}
            if not df_hphi_global.empty:
                df_hphi_dia = df_hphi_global[df_hphi_global['Fecha_Clean'] == fecha_str]
                if not df_hphi_dia.empty:
                    mapa_horas_hphi = df_hphi_dia.groupby(['Puesto_Clean', 'Turno_Clean'])['Duracion_Hs'].sum().to_dict()

            grouped = df_dia.groupby(['Puesto_Clean', 'Turno_Clean', 'Legajo_Clean', 'Material_Clean', 'Tipo_Producto']).agg({
                'Orden_Clean': lambda x: ', '.join(sorted(list(set(x)))),
                'Peso_Unitario': 'first',
                'Unidades_Reales': 'sum',
                'Unid_910': 'sum',
                'Unid_920': 'sum',
                'Ritmo_Final': 'first',
                'Ritmo_Prog_Final': 'first'
            }).reset_index()

            turnos_sap = set(zip(grouped['Puesto_Clean'], grouped['Turno_Clean']))
            turnos_hphi_sin_produccion = []
            for (puesto, turno), horas in mapa_horas_hphi.items():
                if (
                    puesto in (20, 708)
                    or horas <= 0
                    or (puesto, turno) in turnos_sap
                ):
                    continue

                filas_hphi_turno = df_hphi_dia[
                    (df_hphi_dia['Puesto_Clean'] == puesto)
                    & (df_hphi_dia['Turno_Clean'] == turno)
                ]
                productos_hphi = filas_hphi_turno[
                    ['Orden_HPHI', 'Producto_HPHI']
                ].drop_duplicates()
                productos_turno = []
                for _, producto_hphi in productos_hphi.iterrows():
                    orden = producto_hphi['Orden_HPHI']
                    material = producto_hphi['Producto_HPHI']

                    if not material and orden:
                        productos_sap_orden = df_dia.loc[
                            (df_dia['Puesto_Clean'] == puesto)
                            & (df_dia['Orden_Clean'] == orden),
                            'Material_Clean'
                        ].dropna().unique()
                        if len(productos_sap_orden) == 1:
                            material = productos_sap_orden[0]

                    producto_turno = (orden, material)
                    if producto_turno not in productos_turno:
                        productos_turno.append(producto_turno)

                if not productos_turno:
                    productos_turno = [('', '')]

                for orden, material in productos_turno:
                    filas_sap_producto = df_dia[
                        (df_dia['Puesto_Clean'] == puesto)
                        & (df_dia['Material_Clean'] == material)
                    ]
                    if orden:
                        filas_sap_producto_orden = filas_sap_producto[
                            filas_sap_producto['Orden_Clean'] == orden
                        ]
                        if not filas_sap_producto_orden.empty:
                            filas_sap_producto = filas_sap_producto_orden

                    ritmo_info = ritmos_por_puesto_producto.get(
                        (puesto, material),
                        ritmos_por_producto.get(material, {})
                    )
                    ritmo_max = (
                        float(filas_sap_producto.iloc[0]['Ritmo_Final'])
                        if not filas_sap_producto.empty
                        else float(ritmo_info.get('Ritmo_Max', 0.0))
                    )
                    ritmo_prog = (
                        float(filas_sap_producto.iloc[0]['Ritmo_Prog_Final'])
                        if not filas_sap_producto.empty
                        else float(ritmo_info.get('Ritmo_Prog', 0.0))
                    )
                    peso_unitario = (
                        float(filas_sap_producto.iloc[0]['Peso_Unitario'])
                        if not filas_sap_producto.empty
                        else pesos_historicos_por_producto.get(material, 0.0)
                    )

                    turnos_hphi_sin_produccion.append({
                        'Puesto_Clean': puesto,
                        'Turno_Clean': turno,
                        'Legajo_Clean': '',
                        'Material_Clean': material,
                        'Tipo_Producto': (
                            'PT' if len(material) == 6
                            else ('SE' if len(material) == 9 else 'OTRO')
                        ),
                        'Orden_Clean': orden,
                        'Peso_Unitario': peso_unitario,
                        'Unidades_Reales': 0.0,
                        'Unid_910': 0.0,
                        'Unid_920': 0.0,
                        'Ritmo_Final': ritmo_max,
                        'Ritmo_Prog_Final': ritmo_prog
                    })
            if turnos_hphi_sin_produccion:
                grouped = pd.concat(
                    [grouped, pd.DataFrame(turnos_hphi_sin_produccion)],
                    ignore_index=True
                )

            if mapa_910 or mapa_920:
                vistos_910 = set()
                vistos_920 = set()
                nov_910 = []
                nov_920 = []

                for _, r in grouped.iterrows():
                    orden_ref = r['Orden_Clean'].split(',')[0].strip()
                    key = (fecha_str, r['Puesto_Clean'], orden_ref, r['Material_Clean'])

                    if key in mapa_910 and key not in vistos_910:
                        nov_910.append(mapa_910[key])
                        vistos_910.add(key)
                    else:
                        nov_910.append(r['Unid_910'] if key not in vistos_910 else 0.0)

                    if key in mapa_920 and key not in vistos_920:
                        nov_920.append(mapa_920[key])
                        vistos_920.add(key)
                    else:
                        nov_920.append(r['Unid_920'] if key not in vistos_920 else 0.0)

                grouped['Unid_910'] = nov_910
                grouped['Unid_920'] = nov_920

            def calcular_unidades_netas(row):
                if row['Puesto_Clean'] == 20:
                    return 0.0
                return row['Unidades_Reales'] + row['Unid_910'] - row['Unid_920']

            def ajustar_920_puesto20(row):
                if row['Puesto_Clean'] == 20:
                    return row['Unidades_Reales'] if row['Unidades_Reales'] > 0 else row['Unid_920']
                return row['Unid_920']

            grouped['Unid_920'] = grouped.apply(ajustar_920_puesto20, axis=1)
            grouped['Unidades_Reales'] = grouped.apply(lambda r: 0.0 if r['Puesto_Clean'] == 20 else r['Unidades_Reales'], axis=1)
            grouped['Unid_910'] = grouped.apply(lambda r: 0.0 if r['Puesto_Clean'] == 20 else r['Unid_910'], axis=1)
            grouped['Unidades_Producidas_Netas'] = grouped.apply(calcular_unidades_netas, axis=1)

            grouped['Kilos_Reales'] = grouped.apply(
                lambda r: (r['Peso_Unitario'] * r['Unid_920']) if r['Puesto_Clean'] == 20 else (r['Peso_Unitario'] * r['Unidades_Producidas_Netas']),
                axis=1
            )

            grouped['Hs_Productivas'] = grouped.apply(
                lambda r: 0.0 if r['Puesto_Clean'] == 20 else ((r['Unidades_Producidas_Netas'] / r['Ritmo_Final']) if r['Ritmo_Final'] > 0 else 0.0), 
                axis=1
            )

            lista_hs_prog_fila = []
            for (puesto, turno), g_t in grouped.groupby(['Puesto_Clean', 'Turno_Clean']):
                if puesto == 20:
                    for idx, _ in g_t.iterrows():
                        lista_hs_prog_fila.append((idx, 0.0))
                    continue

                if (puesto, turno) in mapa_horas_hphi and mapa_horas_hphi[(puesto, turno)] > 0:
                    h_jornada = mapa_horas_hphi[(puesto, turno)]
                else:
                    h_jornada = 0.0

                tot_prod_t = g_t['Hs_Productivas'].sum()
                n_filas = len(g_t)
                
                for idx, r in g_t.iterrows():
                    if tot_prod_t > 0:
                        h_prog = h_jornada * (r['Hs_Productivas'] / tot_prod_t)
                    else:
                        h_prog = h_jornada / n_filas if n_filas > 0 else h_jornada
                    lista_hs_prog_fila.append((idx, h_prog))

            dict_hs_prog = dict(lista_hs_prog_fila)
            grouped['Hs_Programadas'] = grouped.index.map(dict_hs_prog)

            grouped['Kg_Programado'] = grouped.apply(
                lambda r: 0.0 if r['Puesto_Clean'] == 20 else (r['Hs_Programadas'] * r['Ritmo_Prog_Final'] * r['Peso_Unitario']),
                axis=1
            )

            grouped['Eficiencia_Fila'] = grouped.apply(
                lambda r: 0.0 if r['Puesto_Clean'] == 20 else ((r['Hs_Productivas'] / r['Hs_Programadas']) if r['Hs_Programadas'] > 0 else 0.0),
                axis=1
            )

            grouped['Ritmo_Final'] = grouped.apply(lambda r: 0.0 if r['Puesto_Clean'] == 20 else r['Ritmo_Final'], axis=1)

            grouped_bi = grouped[grouped['Puesto_Clean'] != 20]
            cursor.execute("DELETE FROM eficiencia_bi_diaria WHERE fecha = ?", (fecha_str,))
            for puesto, filas_maquina in grouped_bi.groupby('Puesto_Clean'):
                horas_programadas_bi = float(filas_maquina['Hs_Programadas'].sum())
                horas_productivas_bi = float(filas_maquina['Hs_Productivas'].sum())
                cursor.execute("""
                    INSERT INTO eficiencia_bi_diaria (
                        fecha, puesto_trabajo, horas_programadas, horas_productivas
                    ) VALUES (?, ?, ?, ?)
                """, (
                    fecha_str,
                    int(puesto),
                    horas_programadas_bi,
                    horas_productivas_bi
                ))

            if df_dia_oee.empty:
                continue

            grouped_oee = grouped[
                ~grouped['Puesto_Clean'].isin([20] + maquinas_excluidas)
            ]
            grouped_detalle = grouped[
                ~grouped['Puesto_Clean'].isin(maquinas_excluidas)
            ]

            df_pt = grouped_oee[grouped_oee['Tipo_Producto'] == 'PT']
            df_se = grouped_oee[grouped_oee['Tipo_Producto'] == 'SE']

            kilos_totales_pt = float(round(df_pt['Kilos_Reales'].sum(), 2))
            horas_prod_total = float(round(grouped_oee['Hs_Productivas'].sum(), 2))
            horas_prod_pt = float(round(df_pt['Hs_Productivas'].sum(), 2))
            horas_prod_se = float(round(df_se['Hs_Productivas'].sum(), 2))

            unidades_pt = float(round(df_pt['Unidades_Producidas_Netas'].sum(), 2))
            unidades_se = float(round(df_se['Unidades_Producidas_Netas'].sum(), 2))

            horas_programadas_global = float(round(grouped_oee['Hs_Programadas'].sum(), 2))
            hs_prog_pt = float(round(df_pt['Hs_Programadas'].sum(), 2))
            hs_prog_se = float(round(df_se['Hs_Programadas'].sum(), 2))

            eficiencia_global = float(round((horas_prod_total / horas_programadas_global * 100), 2)) if horas_programadas_global > 0 else 0.0
            eficiencia_pt = float(round((horas_prod_pt / hs_prog_pt * 100), 2)) if hs_prog_pt > 0 else 0.0
            eficiencia_se = float(round((horas_prod_se / hs_prog_se * 100), 2)) if hs_prog_se > 0 else 0.0

            cursor.execute('''
                INSERT INTO historia_diaria_planta (
                    fecha, horas_programadas, horas_producidas_total, 
                    horas_producidas_pt, horas_programadas_pt, 
                    horas_producidas_se, horas_programadas_se,
                    eficiencia_global_porcentaje, eficiencia_pt_porcentaje, eficiencia_se_porcentaje,
                    kilos_totales_pt, unidades_totales_pt, unidades_totales_se, total_filas_sap
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fecha) DO UPDATE SET
                    horas_programadas=excluded.horas_programadas,
                    horas_producidas_total=excluded.horas_producidas_total,
                    horas_producidas_pt=excluded.horas_producidas_pt,
                    horas_programadas_pt=excluded.horas_programadas_pt,
                    horas_producidas_se=excluded.horas_producidas_se,
                    horas_programadas_se=excluded.horas_programadas_se,
                    eficiencia_global_porcentaje=excluded.eficiencia_global_porcentaje,
                    eficiencia_pt_porcentaje=excluded.eficiencia_pt_porcentaje,
                    eficiencia_se_porcentaje=excluded.eficiencia_se_porcentaje,
                    kilos_totales_pt=excluded.kilos_totales_pt,
                    unidades_totales_pt=excluded.unidades_totales_pt,
                    unidades_totales_se=excluded.unidades_totales_se,
                    total_filas_sap=excluded.total_filas_sap
            ''', (fecha_str, horas_programadas_global, horas_prod_total, 
                  horas_prod_pt, hs_prog_pt,
                  horas_prod_se, hs_prog_se,
                  eficiencia_global, eficiencia_pt, eficiencia_se, kilos_totales_pt, unidades_pt, unidades_se, len(df_dia_oee)))

            cursor.execute("DELETE FROM historia_detalle_filas WHERE fecha = ?", (fecha_str,))
            for _, row in grouped_detalle.iterrows():
                cursor.execute('''
                    INSERT INTO historia_detalle_filas (
                        fecha, puesto_trabajo, turno, codigo_maquinista, orden_fabricacion, producto,
                        ritmo_max, ritmo_prog, peso_unitario, unidades_producidas, unidades_cod_910, unidades_cod_920,
                        peso_producido, kg_programado, hs_programadas, hs_productivas, eficiencia, tipo_producto
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (fecha_str, int(row['Puesto_Clean']), str(row['Turno_Clean']), str(row['Legajo_Clean']),
                      str(row['Orden_Clean']), str(row['Material_Clean']), float(row['Ritmo_Final']), float(row['Ritmo_Prog_Final']),
                      float(row['Peso_Unitario']), float(row['Unidades_Reales']), float(row['Unid_910']), float(row['Unid_920']),
                      float(row['Kilos_Reales']), float(row['Kg_Programado']), float(row['Hs_Programadas']), float(row['Hs_Productivas']),
                      float(row['Eficiencia_Fila']), str(row['Tipo_Producto'])))

        conn.commit()
        conn.close()

        return {
            "estado": "exito",
            "mensaje": f"¡Procesados y guardados correctamente {len(fechas_procesadas)} días en la Base de Datos!",
            "fechas_procesadas": fechas_procesadas,
            "ultima_fecha": fechas_procesadas[-1] if fechas_procesadas else None
        }

    except Exception as e:
        print(f"Error procesando SAP/HPHI/910-920: {e}")
        return {"estado": "error", "mensaje": str(e)}

def es_extension_valida(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ['.xlsx', '.xls', '.xlsm', '.csv']

def cargar_automaticamente_desde_carpetas():
    """Busca y procesa automáticamente TODOS los archivos de las tres carpetas."""
    print("\n--- INICIANDO ESCANEO AUTOMÁTICO CONSOLIDADO DE CARPETAS ---")
    
    archivos_sap = []
    if os.path.exists(CARPETA_SAP):
        archivos_sap = [os.path.join(CARPETA_SAP, f) for f in os.listdir(CARPETA_SAP) if es_extension_valida(f)]
    
    if not archivos_sap:
        print("x No se encontraron archivos SAP en la carpeta 50.001.")
        return

    df_hphi_list = []
    if os.path.exists(CARPETA_HPHI):
        f_hphi_files = [os.path.join(CARPETA_HPHI, f) for f in os.listdir(CARPETA_HPHI) if es_extension_valida(f)]
        for path_h in f_hphi_files:
            try:
                print(f"[+] Leyendo HPHI: {os.path.basename(path_h)}...")
                df_temp = pd.read_excel(path_h)
                df_hphi_list.append(df_temp)
            except Exception as eh:
                print(f"    x Error al leer {os.path.basename(path_h)}: {eh}")
    
    df_hphi_consolidado = pd.concat(df_hphi_list, ignore_index=True) if df_hphi_list else None
    if df_hphi_consolidado is not None:
        print(f"    -> HPHI Consolidado con éxito ({len(df_hphi_consolidado)} filas totales).")

    df_dencre_list = []
    if os.path.exists(CARPETA_910_920):
        f_dencre_files = [os.path.join(CARPETA_910_920, f) for f in os.listdir(CARPETA_910_920) if es_extension_valida(f)]
        for path_d in f_dencre_files:
            try:
                print(f"[+] Leyendo DENCRE: {os.path.basename(path_d)}...")
                df_temp_d = pd.read_excel(path_d)
                df_dencre_list.append(df_temp_d)
            except Exception as ed:
                print(f"    x Error al leer {os.path.basename(path_d)}: {ed}")

    df_dencre_consolidado = pd.concat(df_dencre_list, ignore_index=True) if df_dencre_list else None
    if df_dencre_consolidado is not None:
        print(f"    -> DENCRE Consolidado con éxito ({len(df_dencre_consolidado)} filas totales).")

    print(f"\n[+] Procesando {len(archivos_sap)} archivos SAP cruzados...")
    fechas_guardadas = []
    for ruta_sap in sorted(archivos_sap):
        try:
            nombre_f = os.path.basename(ruta_sap)
            print(f" -> Procesando SAP: {nombre_f}...")
            with open(ruta_sap, "rb") as f:
                bytes_sap = f.read()
            
            res = limpiar_y_calcular_sap(
                archivo_sap_bytes=bytes_sap,
                df_hphi_consolidado=df_hphi_consolidado,
                df_910_920_consolidado=df_dencre_consolidado,
                nombre_archivo=nombre_f
            )
            if res.get("fechas_procesadas"):
                fechas_guardadas.extend(res.get("fechas_procesadas"))
            print(f"    Resultado {nombre_f}: {res.get('estado')}")
        except Exception as e:
            print(f"    x Error procesando {ruta_sap}: {e}")

    # IMPRIMIR LAS FECHAS REALES DISPONIBLES EN LA BASE DE DATOS
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT fecha FROM historia_diaria_planta ORDER BY fecha DESC")
    fechas_db = [r[0] for r in cursor.fetchall()]
    conn.close()

    print("\n--- PROCESAMIENTO FINALIZADO ---")
    print(f"[FECHAS EN BASE DE DATOS]: {fechas_db}\n")

def obtener_historial_db():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM historia_diaria_planta ORDER BY fecha DESC", conn)
    conn.close()
    return df.to_dict(orient='records')
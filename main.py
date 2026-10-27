from fastapi import FastAPI, UploadFile, File, Query, Body
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from procesador_sap import limpiar_y_calcular_sap, obtener_historial_db, inicializar_db, cargar_automaticamente_desde_carpetas
import sqlite3
import os
import pandas as pd
import math
from datetime import datetime

app = FastAPI(title="Sistema de Eficiencia de Planta (OEE)")

@app.on_event("startup")
def evento_inicio():
    inicializar_db()
    # DESACTIVADO: Ya no procesa las carpetas al reiniciar; lee directo de la DB.
    # cargar_automaticamente_desde_carpetas()

ORDEN_MAQUINAS_PERSONALIZADO = [26, 1, 2, 278, 178, 115, 213, 113, 35, 4, 3, 6, 218, 212, 112, 12, 117, 80, 708, 20]
ORDEN_MAQUINAS_ANALISIS_16_GP = [
    26, 1, 2, 278, 178, 78, 115, 213, 113, 35, 4,
    3, 6, 218, 18, 109, 12, 112, 212, 80
]
ORDEN_MAQUINAS_DISPONIBILIDAD = [
    26, 1, 2, 278, 178, 78, 115, 213, 113, 35, 352, 4, 3, 6, 218, 18,
    109, 12, 112, 212, 80, 117, 708
]

NOMBRES_MAQUINAS = {
    26: "P15", 1: "LB70", 2: "LB100", 278: "P35", 178: "WireO", 78: "Womako",
    115: "Emblocadora", 213: "Entapadora", 113: "Entapadora", 35: "Will", 4: "Embolsadora",
    352: "Will", 3: "MZKS", 6: "P590", 218: "Cosedora", 18: "Cosedora", 109: "Trilateral",
    12: "Armadora", 112: "Armadora", 212: "Armadora", 80: "Flexo", 117: "Hang", 708: "Polar", 20: "Reproceso Manual"
}

SECTORES_ANALISIS_16_GP = {
    26: {
        1: "Cuerpo de Bobinas",
        2: "Puente y Compensadores",
        3: "Barra de Arqueado",
        4: "Cuerpo Impresor",
        5: "Caja Cpo. Impresor",
        6: "Micro Puntillado",
        7: "Corte Transversal",
        8: "Caja Principal",
        9: "Encimado y Contado",
        10: "Cpo. Mabeg",
        11: "Transporte de Plancha",
        12: "Perforado",
        13: "Corte Trimmer",
        14: "1° Montado",
        15: "Cinta Aerea",
        16: "Cinta espaciadora",
        17: "Cinta Curva",
        18: "Cinta de Descarte",
        19: "Laminero",
        20: "Entrada a Sellador N°1",
        21: "Sellador N°1 (Principal)",
        22: "Horno de Termado N°1",
        23: "Salida de Horno y Derivador",
        24: "Estuchadora",
        25: "Etiquetadoras Cuad. Exp + Staker",
        26: "Embalaje de Exportacion",
        27: "Sellador N°2 (Secundario)",
        28: "Horno de Termado N°2",
        29: "Cinta Salida de Horno 2",
        30: "Encajadora",
        31: "Encintadora"
    },
    278: {
        1: "Cuerpo de Bobinas",
        2: "Puente y Compensadores",
        3: "Barra de Arqueado",
        4: "Cuerpo Impresor",
        5: "Caja Cpo. Impresor",
        6: "Micro Puntillado",
        7: "Corte Transversal",
        8: "Caja Principal",
        9: "Encimado y Contado",
        10: "Cpo. Mabeg",
        11: "Transporte de Plancha",
        12: "Perforado",
        13: "Corte Trimmer",
        14: "1° Montado",
        15: "Cinta Aerea",
        16: "Cinta espaciadora y Prensa",
        17: "Montado de Tapas",
        18: "Perforado de Tapas y Emparejado",
        19: "Lamineros",
        20: "Molinete",
        21: "Cinta Curva",
        22: "Despuntado",
        23: "Transferencia",
        24: "Espiralado",
        25: "Volteador Descartador",
        26: "Intercalador y Cintas de entrada a Staker",
        27: "Staker",
        28: "Cinta de Entrada a Sellador",
        29: "Sellador de Bolsa",
        30: "Horno de Termado",
        31: "Transporte Salida de Horno",
        32: "Encajadora",
        33: "Encintadora",
        34: "Tablero Principal"
    }
}

@app.get("/", response_class=HTMLResponse)
def home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Error: No se encontró index.html</h1>"

@app.get("/logo-angel-estrada.png")
def logo_angel_estrada():
    ruta_logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo-angel-estrada.png")
    return FileResponse(ruta_logo, media_type="image/png")

@app.get("/fechas-disponibles/")
def obtener_fechas_disponibles():
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT fecha FROM historia_diaria_planta WHERE fecha IS NOT NULL AND fecha != '' ORDER BY fecha DESC")
    fechas = [r[0] for r in cursor.fetchall()]
    conn.close()
    return {"estado": "ok", "fechas": fechas}

@app.get("/api/stock-repuestos/")
def obtener_stock_repuestos():
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ejercicio_inicio, mes, valor FROM stock_repuestos_mensual ORDER BY ejercicio_inicio, mes"
        )
        registros = [
            {"ejercicio_inicio": fila[0], "mes": fila[1], "valor": fila[2]}
            for fila in cursor.fetchall()
        ]
        ahora = datetime.now()
        ejercicio_actual = ahora.year if ahora.month >= 7 else ahora.year - 1
        return {
            "estado": "ok",
            "ejercicio_actual": ejercicio_actual,
            "registros": registros
        }
    finally:
        conn.close()

@app.put("/api/stock-repuestos/")
def guardar_stock_repuestos(data: dict = Body(...)):
    if not all(campo in data for campo in ("ejercicio_inicio", "mes", "valor")):
        raise HTTPException(
            status_code=422,
            detail="Debe indicar ejercicio_inicio, mes y valor."
        )

    ejercicio_inicio = data["ejercicio_inicio"]
    mes = data["mes"]
    if isinstance(ejercicio_inicio, bool) or not isinstance(ejercicio_inicio, int) or not 2000 <= ejercicio_inicio <= 2100:
        raise HTTPException(status_code=422, detail="El ejercicio debe ser un año válido.")
    if isinstance(mes, bool) or not isinstance(mes, int) or mes not in range(1, 13):
        raise HTTPException(status_code=422, detail="El mes debe estar entre 1 y 12.")

    valor = data["valor"]
    valor_num = None
    if valor is not None:
        if isinstance(valor, bool):
            raise HTTPException(status_code=422, detail="El valor debe ser un porcentaje entre 0 y 100.")
        try:
            valor_num = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="El valor debe ser un porcentaje entre 0 y 100.")
        if not math.isfinite(valor_num) or not 0 <= valor_num <= 100:
            raise HTTPException(status_code=422, detail="El valor debe ser un porcentaje entre 0 y 100.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        if valor_num is None:
            cursor.execute(
                "DELETE FROM stock_repuestos_mensual WHERE ejercicio_inicio = ? AND mes = ?",
                (ejercicio_inicio, mes)
            )
        else:
            cursor.execute(
                """
                INSERT INTO stock_repuestos_mensual (ejercicio_inicio, mes, valor)
                VALUES (?, ?, ?)
                ON CONFLICT(ejercicio_inicio, mes) DO UPDATE SET valor = excluded.valor
                """,
                (ejercicio_inicio, mes, valor_num)
            )
        conn.commit()
    finally:
        conn.close()
    return {"estado": "ok"}

@app.get("/api/graficos/confiabilidad-stock-repuestos/")
def grafico_confiabilidad_stock_repuestos():
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ejercicio_inicio, mes, valor
            FROM stock_repuestos_mensual
            ORDER BY ejercicio_inicio, mes
        """)
        registros = cursor.fetchall()
    finally:
        conn.close()

    if not registros:
        return {"estado": "vacio"}

    valores_por_ejercicio = {}
    for ejercicio_inicio, mes, valor in registros:
        valores_por_ejercicio.setdefault(int(ejercicio_inicio), {})[int(mes)] = float(valor)

    ejercicios = sorted(valores_por_ejercicio)
    ejercicio_actual = ejercicios[-1]
    ejercicio_anterior = ejercicios[-2] if len(ejercicios) >= 2 else None
    meses_orden = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
    meses_labels = [
        "JULIO", "AGOSTO", "SEPTIEM", "OCTUB.", "NOVIEM.", "DICIEM.",
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO"
    ]

    acumulados_4_ejercicios = []
    for ejercicio in ejercicios[-4:]:
        valores = list(valores_por_ejercicio[ejercicio].values())
        acumulados_4_ejercicios.append({
            "ejercicio": f"{ejercicio % 100:02d}{(ejercicio + 1) % 100:02d}",
            "confiabilidad": round(sum(valores) / len(valores), 2)
        })

    return {
        "estado": "ok",
        "acumulados_4_ejercicios": acumulados_4_ejercicios,
        "meses_labels": meses_labels,
        "mensual_actual": [
            valores_por_ejercicio[ejercicio_actual].get(mes)
            for mes in meses_orden
        ],
        "mensual_anterior": [
            valores_por_ejercicio[ejercicio_anterior].get(mes)
            if ejercicio_anterior is not None else None
            for mes in meses_orden
        ],
        "objetivo_anual": 90.0
    }

@app.get("/api/disponibilidad/")
def obtener_disponibilidad(
    desde: str | None = Query(None, description="Fecha inicial YYYY-MM-DD"),
    hasta: str | None = Query(None, description="Fecha final YYYY-MM-DD")
):
    if (desde is None) != (hasta is None):
        raise HTTPException(status_code=422, detail="Se deben indicar ambas fechas: desde y hasta.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        if desde is None:
            cursor.execute("SELECT MAX(fecha) FROM eventos_hphi")
            ultima_fecha = cursor.fetchone()[0]
            if not ultima_fecha:
                return {
                    "estado": "ok",
                    "desde": "",
                    "hasta": "",
                    "maquinas": [],
                    "totales": None
                }
            hasta = ultima_fecha
            desde = f"{ultima_fecha[:7]}-01"

        try:
            fecha_desde = datetime.strptime(desde, "%Y-%m-%d")
            fecha_hasta = datetime.strptime(hasta, "%Y-%m-%d")
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Las fechas deben tener formato YYYY-MM-DD."
            ) from error

        if fecha_desde.strftime("%Y-%m-%d") != desde or fecha_hasta.strftime("%Y-%m-%d") != hasta:
            raise HTTPException(status_code=422, detail="Las fechas deben tener formato YYYY-MM-DD.")
        if fecha_desde > fecha_hasta:
            raise HTTPException(status_code=422, detail="La fecha DESDE no puede ser posterior a HASTA.")

        cursor.execute("""
            SELECT
                puesto_trabajo,
                SUM(duracion_horas),
                SUM(CASE WHEN concepto = 902 THEN duracion_horas ELSE 0 END),
                SUM(CASE WHEN concepto = 1 THEN duracion_horas ELSE 0 END),
                SUM(CASE WHEN concepto = 14 THEN duracion_horas ELSE 0 END),
                SUM(CASE WHEN concepto = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN concepto = 14 THEN 1 ELSE 0 END)
            FROM eventos_hphi
            WHERE fecha >= ? AND fecha <= ? AND puesto_trabajo != 20
            GROUP BY puesto_trabajo
        """, (desde, hasta))
        agregados = {
            int(row[0]): {
                "horas_totales": float(row[1] or 0),
                "horas_902": float(row[2] or 0),
                "horas_1": float(row[3] or 0),
                "horas_14": float(row[4] or 0),
                "eventos_1": int(row[5] or 0),
                "eventos_14": int(row[6] or 0)
            }
            for row in cursor.fetchall()
        }
    finally:
        conn.close()

    if not agregados:
        return {
            "estado": "ok",
            "desde": desde,
            "hasta": hasta,
            "maquinas": [],
            "totales": None
        }

    puestos = set(NOMBRES_MAQUINAS) - {20}
    puestos.update(agregados)

    def calcular_indicadores(datos):
        cantidad_fallas = datos["eventos_1"] + datos["eventos_14"]
        tiempo_funcionamiento = datos["horas_902"]
        tiempo_inactividad = datos["horas_1"] + datos["horas_14"]
        mtbf = tiempo_funcionamiento / cantidad_fallas if cantidad_fallas else None
        mttr = tiempo_inactividad / cantidad_fallas if cantidad_fallas else None
        if cantidad_fallas:
            disponibilidad = (
                mtbf / (mtbf + mttr) * 100
                if mtbf + mttr > 0
                else 0.0
            )
        elif tiempo_funcionamiento > 0:
            disponibilidad = 100.0
        else:
            disponibilidad = None

        return {
            **datos,
            "mtbf": mtbf,
            "mttr": mttr,
            "disponibilidad": disponibilidad
        }

    filas = []
    for puesto in sorted(
        puestos,
        key=lambda item: (
            ORDEN_MAQUINAS_DISPONIBILIDAD.index(item)
            if item in ORDEN_MAQUINAS_DISPONIBILIDAD
            else len(ORDEN_MAQUINAS_DISPONIBILIDAD) + item
        )
    ):
        datos = agregados.get(puesto, {
            "horas_totales": 0.0,
            "horas_902": 0.0,
            "horas_1": 0.0,
            "horas_14": 0.0,
            "eventos_1": 0,
            "eventos_14": 0
        })
        filas.append({
            "puesto": puesto,
            "nombre": NOMBRES_MAQUINAS.get(puesto, f"Máq {puesto}"),
            **calcular_indicadores(datos)
        })

    totales_base = {
        campo: sum(fila[campo] for fila in filas)
        for campo in (
            "horas_totales", "horas_902", "horas_1", "horas_14", "eventos_1", "eventos_14"
        )
    }
    return {
        "estado": "ok",
        "desde": desde,
        "hasta": hasta,
        "maquinas": filas,
        "totales": calcular_indicadores(totales_base)
    }

@app.get("/api/analisis-16-gp/")
def obtener_analisis_16_gp(
    desde: str = Query(..., description="Fecha inicial YYYY-MM-DD"),
    hasta: str = Query(..., description="Fecha final YYYY-MM-DD")
):
    try:
        fecha_desde = datetime.strptime(desde, "%Y-%m-%d")
        fecha_hasta = datetime.strptime(hasta, "%Y-%m-%d")
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="Las fechas deben tener formato YYYY-MM-DD."
        ) from error

    if fecha_desde.strftime("%Y-%m-%d") != desde or fecha_hasta.strftime("%Y-%m-%d") != hasta:
        raise HTTPException(status_code=422, detail="Las fechas deben tener formato YYYY-MM-DD.")
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=422, detail="La fecha DESDE no puede ser posterior a HASTA.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT puesto_trabajo, concepto, SUM(duracion_horas)
            FROM eventos_hphi
            WHERE fecha >= ? AND fecha <= ?
              AND concepto BETWEEN 1 AND 16
              AND puesto_trabajo NOT IN (117, 20)
            GROUP BY puesto_trabajo, concepto
            HAVING SUM(duracion_horas) > 0
            ORDER BY puesto_trabajo, concepto
        """, (desde, hasta))
        registros = cursor.fetchall()
        cursor.execute("""
            SELECT puesto_trabajo, concepto, TRIM(descripcion), COUNT(*), SUM(duracion_horas)
            FROM eventos_hphi
            WHERE fecha >= ? AND fecha <= ?
              AND concepto BETWEEN 1 AND 16
              AND puesto_trabajo NOT IN (117, 20)
              AND TRIM(descripcion) != ''
            GROUP BY puesto_trabajo, concepto, TRIM(descripcion)
            HAVING SUM(duracion_horas) > 0
        """, (desde, hasta))
        registros_observaciones = cursor.fetchall()
    finally:
        conn.close()

    grupos_codigos = (
        (5, 13), (4, 6, 15), (10, 11, 16), (1, 14),
        (2,), (3, 8), (7, 9, 12)
    )
    grupo_por_codigo = {
        codigo: indice
        for indice, codigos in enumerate(grupos_codigos)
        for codigo in codigos
    }
    observaciones_por_maquina = {}
    sectores_por_maquina = {}
    for puesto, codigo, descripcion, eventos, horas in registros_observaciones:
        descripcion = " ".join(str(descripcion or "").split())
        if not descripcion:
            continue

        puesto = int(puesto)
        if not any(caracter.isalpha() for caracter in descripcion):
            sectores = SECTORES_ANALISIS_16_GP.get(puesto)
            codigos_sector = [
                codigo_sector.strip()
                for codigo_sector in (
                    descripcion.replace(",", "/")
                    .replace(";", "/")
                    .replace("-", "/")
                    .split("/")
                )
            ]
            if (
                sectores is None
                or any(not codigo_sector.isdigit() for codigo_sector in codigos_sector)
                or any(int(codigo_sector) not in sectores for codigo_sector in codigos_sector)
            ):
                continue
            grupo = grupo_por_codigo.get(int(codigo))
            if grupo is None:
                continue
            sectores_grupo = sectores_por_maquina.setdefault(puesto, {}).setdefault(grupo, {})
            for codigo_sector in dict.fromkeys(codigos_sector):
                sector = int(codigo_sector)
                observacion_sector = sectores_grupo.setdefault(
                    sector, {"horas": 0.0, "eventos": 0}
                )
                observacion_sector["horas"] += float(horas or 0)
                observacion_sector["eventos"] += int(eventos or 0)
            continue

        grupo = grupo_por_codigo.get(int(codigo))
        if grupo is None:
            continue
        clave = (grupo, descripcion.casefold())
        observaciones_grupo = observaciones_por_maquina.setdefault(puesto, {})
        observacion = observaciones_grupo.get(clave)
        if observacion is None:
            observacion = {
                "descripcion": descripcion,
                "horas": 0.0,
                "eventos": 0,
                "variante_horas": -1.0,
                "variante_eventos": -1
            }
            observaciones_grupo[clave] = observacion

        observacion["horas"] += float(horas or 0)
        observacion["eventos"] += int(eventos or 0)
        if (float(horas or 0), int(eventos or 0)) > (
            observacion["variante_horas"],
            observacion["variante_eventos"]
        ):
            observacion["descripcion"] = descripcion
            observacion["variante_horas"] = float(horas or 0)
            observacion["variante_eventos"] = int(eventos or 0)

    observaciones_top_por_maquina = {}
    for puesto, observaciones_grupo in observaciones_por_maquina.items():
        observaciones_top_por_maquina[puesto] = [None] * len(grupos_codigos)
        for (grupo, _), observacion in observaciones_grupo.items():
            actual = observaciones_top_por_maquina[puesto][grupo]
            if actual is None or (
                observacion["horas"], observacion["eventos"]
            ) > (actual["horas"], actual["eventos"]):
                observaciones_top_por_maquina[puesto][grupo] = {
                    "descripcion": observacion["descripcion"],
                    "horas": round(observacion["horas"], 2),
                    "eventos": observacion["eventos"],
                    "sectores": []
                }

    for puesto, sectores_por_grupo in sectores_por_maquina.items():
        observaciones_grupos = observaciones_top_por_maquina.setdefault(
            puesto, [None] * len(grupos_codigos)
        )
        for grupo, sectores in sectores_por_grupo.items():
            observacion = observaciones_grupos[grupo]
            if observacion is None:
                observacion = {
                    "descripcion": "",
                    "horas": 0.0,
                    "eventos": 0,
                    "sectores": []
                }
                observaciones_grupos[grupo] = observacion
            observacion["sectores"] = [
                {
                    "codigo": codigo_sector,
                    "descripcion": SECTORES_ANALISIS_16_GP[puesto][codigo_sector],
                    "horas": round(datos["horas"], 2),
                    "eventos": datos["eventos"]
                }
                for codigo_sector, datos in sorted(
                    sectores.items(),
                    key=lambda item: (-item[1]["horas"], item[0])
                )
            ]

    horas_por_maquina = {}
    for puesto, codigo, horas in registros:
        puesto = int(puesto)
        if puesto not in horas_por_maquina:
            horas_por_maquina[puesto] = [0.0] * 16
        horas_por_maquina[puesto][int(codigo) - 1] = round(float(horas), 2)

    maquinas = [
        {
            "puesto": puesto,
            "nombre": NOMBRES_MAQUINAS.get(puesto, f"Máq {puesto}"),
            "horas_por_codigo": horas,
            "sectores_catalogo": [
                {"codigo": codigo, "descripcion": descripcion}
                for codigo, descripcion in SECTORES_ANALISIS_16_GP.get(puesto, {}).items()
            ],
            "observaciones_por_grupo": observaciones_top_por_maquina.get(
                puesto, [None] * len(grupos_codigos)
            )
        }
        for puesto, horas in sorted(
            horas_por_maquina.items(),
            key=lambda item: (
                ORDEN_MAQUINAS_ANALISIS_16_GP.index(item[0])
                if item[0] in ORDEN_MAQUINAS_ANALISIS_16_GP
                else len(ORDEN_MAQUINAS_ANALISIS_16_GP) + item[0]
            )
        )
    ]
    return {
        "estado": "ok",
        "desde": desde,
        "hasta": hasta,
        "maquinas": maquinas
    }

@app.get("/api/baja-improductividad/maquinas/")
def obtener_maquinas_baja_improductividad(
    mes: str | None = Query(None, description="Mes a consultar con formato YYYY-MM")
):
    if mes is not None:
        try:
            fecha_seleccionada = datetime.strptime(mes, "%Y-%m")
            if fecha_seleccionada.strftime("%Y-%m") != mes:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="El mes debe tener formato YYYY-MM.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        if mes is None:
            cursor.execute("""
                SELECT MAX(fecha) FROM (
                    SELECT fecha FROM historia_detalle_filas
                    UNION ALL SELECT fecha FROM eficiencia_bi_diaria
                    UNION ALL SELECT fecha FROM eventos_hphi WHERE puesto_trabajo = 708
                    UNION ALL SELECT fecha FROM historia_diaria_planta
                )
            """)
            ultima_fecha = cursor.fetchone()[0]
            mes = ultima_fecha[:7] if ultima_fecha else None

        cursor.execute("""
            SELECT puesto_trabajo FROM maquinas_sap
            WHERE puesto_trabajo != 20
        """)
        puestos = [int(row[0]) for row in cursor.fetchall()]

        eficiencias = {}
        if mes:
            desde = f"{mes}-01"
            hasta = (pd.Period(mes, freq="M").end_time).strftime("%Y-%m-%d")

            cursor.execute("""
                SELECT puesto_trabajo, SUM(hs_programadas), SUM(hs_productivas)
                FROM historia_detalle_filas
                WHERE fecha >= ? AND fecha <= ? AND puesto_trabajo != 20
                GROUP BY puesto_trabajo
            """, (desde, hasta))
            detalle_historico = {
                int(puesto): (horas_programadas or 0.0, horas_productivas or 0.0)
                for puesto, horas_programadas, horas_productivas in cursor.fetchall()
            }

            cursor.execute("""
                SELECT puesto_trabajo, SUM(horas_programadas), SUM(horas_productivas)
                FROM eficiencia_bi_diaria
                WHERE fecha >= ? AND fecha <= ? AND puesto_trabajo NOT IN (20, 708)
                GROUP BY puesto_trabajo
            """, (desde, hasta))
            detalle_bi = {
                int(puesto): (horas_programadas or 0.0, horas_productivas or 0.0)
                for puesto, horas_programadas, horas_productivas in cursor.fetchall()
            }

            cursor.execute("""
                SELECT
                    SUM(CASE WHEN concepto = 902 THEN duracion_horas ELSE 0 END),
                    SUM(duracion_horas)
                FROM eventos_hphi
                WHERE puesto_trabajo = 708 AND fecha >= ? AND fecha <= ?
            """, (desde, hasta))
            horas_902, horas_totales = cursor.fetchone()
            if horas_totales and horas_totales > 0:
                eficiencias[708] = round(horas_902 / horas_totales * 100.0, 2)

            for puesto in puestos:
                if puesto == 708:
                    continue
                if puesto in {16, 18, 44, 80, 91, 108, 117, 118}:
                    horas_programadas, horas_productivas = detalle_bi.get(
                        puesto,
                        detalle_historico.get(puesto, (0.0, 0.0))
                    )
                else:
                    horas_programadas, horas_productivas = detalle_historico.get(
                        puesto,
                        detalle_bi.get(puesto, (0.0, 0.0))
                    )
                if horas_programadas > 0:
                    eficiencias[puesto] = round(
                        horas_productivas / horas_programadas * 100.0,
                        2
                    )
    finally:
        conn.close()

    puestos.sort(key=lambda puesto: (
        ORDEN_MAQUINAS_PERSONALIZADO.index(puesto)
        if puesto in ORDEN_MAQUINAS_PERSONALIZADO
        else len(ORDEN_MAQUINAS_PERSONALIZADO) + puesto
    ))
    return {
        "estado": "ok",
        "mes": mes,
        "maquinas": [
            {
                "puesto": puesto,
                "nombre": NOMBRES_MAQUINAS.get(puesto, f"Máq {puesto}"),
                "eficiencia": eficiencias.get(puesto)
            }
            for puesto in puestos
        ]
    }

@app.post("/procesar-sap/")
async def procesar_sap(
    archivos: list[UploadFile] = File(...)
):
    try:
        contenido_sap = None
        contenido_hphi = None
        contenido_910_920 = None
        nombre_f = ""

        # Identificar dinámicamente cada archivo según su nombre
        for f in archivos:
            nombre_lower = f.filename.lower()
            bytes_f = await f.read()
            
            if "hphi" in nombre_lower or "hp" in nombre_lower:
                contenido_hphi = bytes_f
            elif "dencre" in nombre_lower or "den" in nombre_lower or "910" in nombre_lower:
                contenido_910_920 = bytes_f
            else:
                contenido_sap = bytes_f
                nombre_f = f.filename

        return limpiar_y_calcular_sap(
            archivo_sap_bytes=contenido_sap,
            archivo_hphi_bytes=contenido_hphi,
            archivo_910_920_bytes=contenido_910_920,
            nombre_archivo=nombre_f
        )
    except Exception as e:
        return {"estado": "error", "mensaje": f"Excepción en el servidor: {str(e)}"}

@app.get("/historial-diario/")
def consultar_historial_diario(fecha: str = Query(..., description="Fecha YYYY-MM-DD")):
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    cursor = conn.cursor()

    fecha_query = fecha.strip()
    cursor.execute("""
        SELECT fecha, horas_programadas, horas_producidas_total, 
               horas_producidas_pt, horas_programadas_pt,
               horas_producidas_se, horas_programadas_se,
               eficiencia_global_porcentaje, eficiencia_pt_porcentaje, eficiencia_se_porcentaje,
               kilos_totales_pt, unidades_totales_pt, unidades_totales_se
        FROM historia_diaria_planta WHERE fecha = ? OR fecha LIKE ?
    """, (fecha_query, f"%{fecha_query}%"))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return {"estado": "sin_datos", "fecha": fecha_query}

    fecha_real_db = row[0]

    cursor.execute("""
        SELECT puesto_trabajo, turno, codigo_maquinista, orden_fabricacion, producto,
               ritmo_max, peso_unitario, unidades_producidas, unidades_cod_910, unidades_cod_920,
               kg_programado, peso_producido, hs_programadas, hs_productivas, eficiencia,
               tipo_producto, ritmo_prog
        FROM historia_detalle_filas
        WHERE fecha = ?
    """, (fecha_real_db,))
    filas_detalle = cursor.fetchall()
    conn.close()

    detalle_maquinas = []
    hs_prog_pt_calc = 0.0
    hs_prog_se_calc = 0.0

    for f in filas_detalle:
        puesto = f[0]
        hs_prog = f[12] or 0.0
        tipo_p = str(f[15]) if len(f) > 15 else ('PT' if len(str(f[4]).strip()) == 6 else 'SE')
        
        if puesto != 20:
            if tipo_p == 'PT':
                hs_prog_pt_calc += hs_prog
            elif tipo_p == 'SE':
                hs_prog_se_calc += hs_prog

        detalle_maquinas.append({
            "puesto": f[0],
            "turno": f[1],
            "codigoMaquinista": f[2],
            "ordenFabricacion": f[3],
            "producto": f[4],
            "ritmoMax": f[5],
            "pesoUnitario": f[6],
            "unidadesProducidas": f[7],
            "unidades910": f[8],
            "unidades920": f[9],
            "programado": (
                (f[12] or 0.0) * (f[16] or 0.0)
                if tipo_p == "SE"
                else (f[12] or 0.0) * (f[16] or 0.0) * (f[6] or 0.0)
            ),
            "unidadProgramado": "Un" if tipo_p == "SE" else "Kg",
            "pesoProducido": f[11],
            "hsProgramadas": f[12],
            "hsProductivas": f[13],
            "eficiencia": f[14]
        })

    def obtener_indice_puesto(item):
        puesto = item["puesto"]
        if puesto in ORDEN_MAQUINAS_PERSONALIZADO:
            return (0, ORDEN_MAQUINAS_PERSONALIZADO.index(puesto))
        return (1, puesto)

    detalle_maquinas.sort(key=obtener_indice_puesto)

    horas_prog_pt_final = row[4] if (row[4] and row[4] > 0) else hs_prog_pt_calc
    horas_prog_se_final = row[6] if (row[6] and row[6] > 0) else hs_prog_se_calc

    return {
        "estado": "ok",
        "fecha": row[0],
        "horas_programadas": row[1],
        "horas_producidas_total": row[2],
        "horas_producidas_pt": row[3],
        "horas_programadas_pt": round(horas_prog_pt_final, 2),
        "horas_producidas_se": row[5],
        "horas_programadas_se": round(horas_prog_se_final, 2),
        "eficiencia_global_porcentaje": row[7],
        "eficiencia_pt_porcentaje": row[8],
        "eficiencia_se_porcentaje": row[9],
        "kilos_totales_pt": row[10],
        "unidades_totales_pt": row[11],
        "unidades_totales_se": row[12],
        "filas_detalle": detalle_maquinas
    }

@app.get("/ultimo-registro/")
def obtener_ultimo_registro():
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    cursor = conn.cursor()
    cursor.execute("SELECT fecha FROM historia_diaria_planta ORDER BY fecha DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"estado": "vacio"}
    return {"estado": "ok", "fecha": row[0]}

@app.get("/acumulado/")
def consultar_acumulado(desde: str = Query(...), hasta: str = Query(...)):
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    cursor = conn.cursor()

    cursor.execute("SELECT puesto_trabajo, objetivo_anual, resultado_anterior FROM metas_maquina")
    mapa_metas = {r[0]: {"objetivo_anual": r[1], "resultado_anterior": r[2]} for r in cursor.fetchall()}
    cursor.execute("""
        SELECT objetivo_anual, resultado_anterior, objetivo_mes_kg
        FROM metas_planta WHERE id = 1
    """)
    meta_planta = cursor.fetchone() or (0.0, 0.0, 0.0)

    query = """
        SELECT puesto_trabajo, tipo_producto,
               SUM(hs_programadas) as total_h_prog,
               SUM(hs_productivas) as total_h_prod,
               SUM(kg_programado) as total_kg_prog,
               SUM(peso_producido) as total_kg_real,
               SUM(unidades_cod_910 * peso_unitario) as total_kg_910,
               SUM(unidades_cod_920 * peso_unitario) as total_kg_920
        FROM historia_detalle_filas
        WHERE fecha >= ? AND fecha <= ?
        GROUP BY puesto_trabajo, tipo_producto
    """
    cursor.execute(query, (desde, hasta))
    filas = cursor.fetchall()
    conn.close()

    total_hs_perdidas_planta = 0.0
    agrupado = []

    for f in filas:
        puesto = f[0]
        tipo_p = f[1]
        h_prog = f[2] or 0.0
        h_prod = f[3] or 0.0
        kg_prog = f[4] or 0.0
        kg_real = f[5] or 0.0
        kg_910 = f[6] or 0.0
        kg_920 = f[7] or 0.0

        hs_perd = max(0.0, h_prog - h_prod) if puesto != 20 else 0.0
        if puesto != 20:
            total_hs_perdidas_planta += hs_perd

        agrupado.append({
            "puesto": puesto,
            "tipo_producto": tipo_p,
            "nombre_maquina": NOMBRES_MAQUINAS.get(puesto, f"Máq {puesto}"),
            "h_prog": h_prog,
            "h_prod": h_prod,
            "kg_prog": kg_prog,
            "kg_real": kg_real,
            "kg_910": kg_910,
            "kg_920": kg_920,
            "hs_perdidas": hs_perd
        })

    resultado_pt = []
    resultado_se = []
    resultado_reproceso = []

    total_h_prog_planta = 0.0
    total_h_prod_planta = 0.0
    for d in agrupado:
        puesto = d["puesto"]
        tipo_p = d["tipo_producto"]
        h_prog = d["h_prog"]
        h_prod = d["h_prod"]
        kg_prog = d["kg_prog"]
        kg_real = d["kg_real"]

        acumulado_pct = (h_prod / h_prog * 100.0) if h_prog > 0 else 0.0
        perdidas_pct = (d["hs_perdidas"] / total_hs_perdidas_planta * 100.0) if total_hs_perdidas_planta > 0 else 0.0
        desvio_kg = kg_real - kg_prog
        kg_hora_real = (kg_real / h_prod) if h_prod > 0 else 0.0
        cumpl_progr = (kg_real / kg_prog * 100.0) if kg_prog > 0 else 0.0
        diferencia_kg = d["kg_910"] - d["kg_920"]

        meta = mapa_metas.get(puesto, {"objetivo_anual": 0.0, "resultado_anterior": 0.0})

        if puesto != 20:
            total_h_prog_planta += h_prog
            total_h_prod_planta += h_prod

        item = {
            "puesto": puesto,
            "maquina_label": f"{d['nombre_maquina']} {str(puesto).zfill(3)}",
            "objetivo_anual": meta["objetivo_anual"],
            "resultado_anterior": meta["resultado_anterior"],
            "acumulado_pct": round(acumulado_pct, 2),
            "perdidas_pct": round(perdidas_pct, 2),
            "desvio_kg": round(desvio_kg, 2),
            "h_prog": round(h_prog, 2),
            "h_prod": round(h_prod, 2),
            "kg_prog": round(kg_prog, 2),
            "kg_real": round(kg_real, 2),
            "kg_hora_real": round(kg_hora_real, 2),
            "cumpl_progr": round(cumpl_progr, 2),
            "kg_910": round(d["kg_910"], 2),
            "kg_920": round(d["kg_920"], 2),
            "diferencia": round(diferencia_kg, 2),
            "tipo_producto": tipo_p
        }

        if puesto == 20:
            resultado_reproceso.append(item)
        elif tipo_p == "PT":
            resultado_pt.append(item)
        else:
            resultado_se.append(item)

    def sort_key(x):
        p = x["puesto"]
        return ORDEN_MAQUINAS_PERSONALIZADO.index(p) if p in ORDEN_MAQUINAS_PERSONALIZADO else 999

    resultado_pt.sort(key=sort_key)
    resultado_se.sort(key=sort_key)

    acumulado_planta_pct = (total_h_prod_planta / total_h_prog_planta * 100.0) if total_h_prog_planta > 0 else 0.0

    return {
        "estado": "ok",
        "desde": desde,
        "hasta": hasta,
        "planta_objetivo_anual": meta_planta[0],
        "planta_resultado_anterior": meta_planta[1],
        "planta_objetivo_mes_kg": meta_planta[2],
        "planta_acumulado": round(acumulado_planta_pct, 1),
        "maquinas_pt": resultado_pt,
        "maquinas_se": resultado_se,
        "maquinas_reproceso": resultado_reproceso
    }

@app.post("/guardar-meta-planta/")
def guardar_meta_planta(data: dict = Body(...)):
    campos = {
        "objetivo_anual": data.get("objetivo_anual"),
        "resultado_anterior": data.get("resultado_anterior"),
        "objetivo_mes_kg": data.get("objetivo_mes_kg")
    }
    valores = {}

    for campo, valor in campos.items():
        if campo not in data:
            continue
        if isinstance(valor, bool):
            raise HTTPException(status_code=422, detail=f"{campo} debe ser un número.")
        try:
            valor_num = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{campo} debe ser un número.")
        if not math.isfinite(valor_num):
            raise HTTPException(status_code=422, detail=f"{campo} debe ser un número finito.")
        valores[campo] = valor_num

    if not valores:
        raise HTTPException(status_code=422, detail="Debe indicar al menos un valor para guardar.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        asignaciones = ", ".join(f"{campo} = ?" for campo in valores)
        cursor.execute(
            f"UPDATE metas_planta SET {asignaciones} WHERE id = 1",
            tuple(valores.values())
        )
        conn.commit()
    finally:
        conn.close()
    return {"estado": "ok"}

@app.post("/guardar-meta/")
def guardar_meta(data: dict = Body(...)):
    puesto = data.get("puesto")
    
    conn = sqlite3.connect("eficiencia_historia.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT objetivo_anual, resultado_anterior FROM metas_maquina WHERE puesto_trabajo = ?", (puesto,))
    row = cursor.fetchone()
    
    obj_anual = data.get("objetivo_anual")
    res_anterior = data.get("resultado_anterior")
    
    if row:
        if obj_anual is None:
            obj_anual = row[0]
        if res_anterior is None:
            res_anterior = row[1]
    else:
        if obj_anual is None:
            obj_anual = 0.0
        if res_anterior is None:
            res_anterior = 0.0

    cursor.execute("""
        INSERT INTO metas_maquina (puesto_trabajo, objetivo_anual, resultado_anterior)
        VALUES (?, ?, ?)
        ON CONFLICT(puesto_trabajo) DO UPDATE SET
            objetivo_anual=excluded.objetivo_anual,
            resultado_anterior=excluded.resultado_anterior
    """, (puesto, float(obj_anual), float(res_anterior)))
    
    conn.commit()
    conn.close()
    return {"estado": "ok"}

@app.get("/api/graficos/eficiencia-mensual/")
def grafico_eficiencia_mensual():
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    
    df = pd.read_sql_query("SELECT fecha, horas_programadas, horas_producidas_total FROM historia_diaria_planta WHERE fecha IS NOT NULL AND fecha != ''", conn)
    conn.close()

    if df.empty:
        return {"estado": "vacio"}

    df['fecha_dt'] = pd.to_datetime(df['fecha'], errors='coerce')
    df = df.dropna(subset=['fecha_dt']).copy()

    max_fecha = df['fecha_dt'].max()
    primer_dia_mes_actual = max_fecha.replace(day=1)
    df_cerrado = df[df['fecha_dt'] < primer_dia_mes_actual].copy()

    if df_cerrado.empty:
        df_cerrado = df.copy()

    def obtener_ejercicio_label(dt):
        year = dt.year
        month = dt.month
        if month >= 7:
            start_y = year % 100
            end_y = (year + 1) % 100
        else:
            start_y = (year - 1) % 100
            end_y = year % 100
        return f"{start_y:02d}{end_y:02d}"

    df['ejercicio'] = df['fecha_dt'].apply(obtener_ejercicio_label)
    df_cerrado['ejercicio'] = df_cerrado['fecha_dt'].apply(obtener_ejercicio_label)
    
    ejercicios_disponibles = sorted(df['ejercicio'].unique())
    if not ejercicios_disponibles:
        return {"estado": "vacio"}

    ejercicio_actual = ejercicios_disponibles[-1]
    ejercicio_anterior = ejercicios_disponibles[-2] if len(ejercicios_disponibles) >= 2 else None

    acumulados_4_ejercicios = []
    ultimos_4_ejercicios = ejercicios_disponibles[-4:]
    for ej in ultimos_4_ejercicios:
        if ej == ejercicio_actual:
            df_ej = df_cerrado[df_cerrado['ejercicio'] == ej]
        else:
            df_ej = df[df['ejercicio'] == ej]

        h_prog = df_ej['horas_programadas'].sum()
        h_prod = df_ej['horas_producidas_total'].sum()
        pct = (h_prod / h_prog * 100.0) if h_prog > 0 else 0.0
        acumulados_4_ejercicios.append({
            "ejercicio": ej,
            "eficiencia": round(pct, 2)
        })

    meses_orden = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
    meses_nombres = ["JULIO", "AGOSTO", "SEPTIEM", "OCTUB.", "NOVIEM.", "DICIEM.", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO"]

    mensual_actual = []
    mensual_anterior = []

    for m in meses_orden:
        df_m_act = df_cerrado[(df_cerrado['ejercicio'] == ejercicio_actual) & (df_cerrado['fecha_dt'].dt.month == m)]
        if not df_m_act.empty:
            h_p = df_m_act['horas_programadas'].sum()
            h_pr = df_m_act['horas_producidas_total'].sum()
            mensual_actual.append(round((h_pr / h_p * 100.0), 2) if h_p > 0 else None)
        else:
            mensual_actual.append(None)

        if ejercicio_anterior:
            df_m_ant = df[(df['ejercicio'] == ejercicio_anterior) & (df['fecha_dt'].dt.month == m)]
            if not df_m_ant.empty:
                h_p_ant = df_m_ant['horas_programadas'].sum()
                h_pr_ant = df_m_ant['horas_producidas_total'].sum()
                mensual_anterior.append(round((h_pr_ant / h_p_ant * 100.0), 2) if h_p_ant > 0 else None)
            else:
                mensual_anterior.append(None)
        else:
            mensual_anterior.append(None)

    return {
        "estado": "ok",
        "acumulados_4_ejercicios": acumulados_4_ejercicios,
        "meses_labels": meses_nombres,
        "mensual_actual": mensual_actual,
        "mensual_anterior": mensual_anterior,
        "objetivo_anual": 45.60
    }

@app.get("/api/graficos/disponibilidad-mensual/")
def grafico_disponibilidad_mensual():
    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        df = pd.read_sql_query("""
            SELECT
                substr(fecha, 1, 7) AS mes,
                SUM(CASE WHEN concepto = 902 THEN duracion_horas ELSE 0 END) AS horas_902,
                SUM(CASE WHEN concepto IN (1, 14) THEN duracion_horas ELSE 0 END) AS horas_inactividad,
                SUM(CASE WHEN concepto IN (1, 14) THEN 1 ELSE 0 END) AS eventos_falla
            FROM eventos_hphi
            WHERE fecha IS NOT NULL AND fecha != '' AND puesto_trabajo != 20
            GROUP BY substr(fecha, 1, 7)
            ORDER BY mes
        """, conn)
    finally:
        conn.close()

    if df.empty:
        return {"estado": "vacio"}

    df["fecha_dt"] = pd.to_datetime(df["mes"], format="%Y-%m", errors="coerce")
    df = df.dropna(subset=["fecha_dt"]).copy()
    if df.empty:
        return {"estado": "vacio"}

    max_fecha = df["fecha_dt"].max()
    primer_dia_mes_actual = max_fecha.replace(day=1)
    df_cerrado = df[df["fecha_dt"] < primer_dia_mes_actual].copy()
    if df_cerrado.empty:
        df_cerrado = df.copy()

    df["ejercicio_inicio"] = df["fecha_dt"].apply(
        lambda fecha: fecha.year if fecha.month >= 7 else fecha.year - 1
    )
    df_cerrado["ejercicio_inicio"] = df_cerrado["fecha_dt"].apply(
        lambda fecha: fecha.year if fecha.month >= 7 else fecha.year - 1
    )
    ejercicios_disponibles = sorted(int(anio) for anio in df["ejercicio_inicio"].unique())
    ejercicio_actual = ejercicios_disponibles[-1]
    ejercicio_anterior = ejercicios_disponibles[-2] if len(ejercicios_disponibles) >= 2 else None
    ultimos_ejercicios = ejercicios_disponibles[-4:]

    def calcular_disponibilidad(filas):
        horas_funcionamiento = float(filas["horas_902"].sum())
        horas_inactividad = float(filas["horas_inactividad"].sum())
        eventos_falla = int(filas["eventos_falla"].sum())
        if eventos_falla:
            mtbf = horas_funcionamiento / eventos_falla
            mttr = horas_inactividad / eventos_falla
            return round(mtbf / (mtbf + mttr) * 100.0, 2) if mtbf + mttr > 0 else None
        return 100.0 if horas_funcionamiento > 0 else None

    acumulados_4_ejercicios = []
    for ejercicio in ultimos_ejercicios:
        datos_ejercicio = df_cerrado if ejercicio == ejercicio_actual else df
        datos_ejercicio = datos_ejercicio[
            datos_ejercicio["ejercicio_inicio"] == ejercicio
        ]
        acumulados_4_ejercicios.append({
            "ejercicio": f"{ejercicio % 100:02d}{(ejercicio + 1) % 100:02d}",
            "disponibilidad": calcular_disponibilidad(datos_ejercicio)
        })

    meses_orden = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
    meses_labels = [
        "JULIO", "AGOSTO", "SEPTIEM", "OCTUB.", "NOVIEM.", "DICIEM.",
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO"
    ]
    mensual_actual = []
    mensual_anterior = []
    for numero_mes in meses_orden:
        datos_mes_actual = df_cerrado[
            (df_cerrado["ejercicio_inicio"] == ejercicio_actual)
            & (df_cerrado["fecha_dt"].dt.month == numero_mes)
        ]
        mensual_actual.append(
            calcular_disponibilidad(datos_mes_actual) if not datos_mes_actual.empty else None
        )

        if ejercicio_anterior is None:
            mensual_anterior.append(None)
            continue
        datos_mes_anterior = df[
            (df["ejercicio_inicio"] == ejercicio_anterior)
            & (df["fecha_dt"].dt.month == numero_mes)
        ]
        mensual_anterior.append(
            calcular_disponibilidad(datos_mes_anterior) if not datos_mes_anterior.empty else None
        )

    return {
        "estado": "ok",
        "acumulados_4_ejercicios": acumulados_4_ejercicios,
        "meses_labels": meses_labels,
        "mensual_actual": mensual_actual,
        "mensual_anterior": mensual_anterior,
        "objetivo_anual": 98.0
    }

@app.get("/api/graficos/paradas-mensuales/")
def grafico_paradas_mensuales(
    mes: str | None = Query(None, description="Mes a mostrar con formato YYYY-MM")
):
    if mes is not None:
        try:
            fecha_seleccionada = datetime.strptime(mes, "%Y-%m")
            if fecha_seleccionada.strftime("%Y-%m") != mes:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="El mes debe tener formato YYYY-MM.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        cursor = conn.cursor()
        if mes is None:
            cursor.execute("""
                SELECT MAX(substr(fecha, 1, 7))
                FROM eventos_hphi
                WHERE concepto IN (1, 14) AND puesto_trabajo != 20
            """)
            mes = cursor.fetchone()[0]
            if not mes:
                return {"estado": "vacio", "maquinas": [], "maquinas_top": []}

        desde = f"{mes}-01"
        hasta = pd.Period(mes, freq="M").end_time.strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT
                puesto_trabajo,
                SUM(CASE WHEN concepto = 1 THEN duracion_horas ELSE 0 END) AS horas_codigo_1,
                SUM(CASE WHEN concepto = 14 THEN duracion_horas ELSE 0 END) AS horas_codigo_14
            FROM eventos_hphi
            WHERE fecha >= ? AND fecha <= ?
              AND concepto IN (1, 14)
              AND puesto_trabajo != 20
            GROUP BY puesto_trabajo
            HAVING SUM(duracion_horas) > 0
            ORDER BY SUM(duracion_horas) DESC, puesto_trabajo
        """, (desde, hasta))
        datos_maquinas = cursor.fetchall()

        maquinas = [
            {
                "puesto": int(puesto),
                "nombre": NOMBRES_MAQUINAS.get(int(puesto), f"Máq {int(puesto)}"),
                "horas_codigo_1": round(float(horas_1 or 0), 2),
                "horas_codigo_14": round(float(horas_14 or 0), 2),
                "horas_totales": round(float((horas_1 or 0) + (horas_14 or 0)), 2)
            }
            for puesto, horas_1, horas_14 in datos_maquinas
        ]
        maquinas_top = maquinas[:3]
        if maquinas_top:
            placeholders = ",".join("?" for _ in maquinas_top)
            cursor.execute(f"""
                SELECT
                    puesto_trabajo,
                    COALESCE(NULLIF(TRIM(descripcion), ''), 'Sin descripción') AS causa,
                    SUM(duracion_horas) AS horas
                FROM eventos_hphi
                WHERE fecha >= ? AND fecha <= ?
                  AND concepto IN (1, 14)
                  AND puesto_trabajo IN ({placeholders})
                GROUP BY puesto_trabajo, causa
                HAVING SUM(duracion_horas) > 0
                ORDER BY puesto_trabajo, horas DESC, causa
            """, (desde, hasta, *(maquina["puesto"] for maquina in maquinas_top)))
            causas_por_puesto = {}
            for puesto, causa, horas in cursor.fetchall():
                causas_por_puesto.setdefault(int(puesto), []).append({
                    "causa": causa,
                    "horas": float(horas)
                })

            for maquina in maquinas_top:
                causas = causas_por_puesto.get(maquina["puesto"], [])
                total_horas = sum(causa["horas"] for causa in causas)
                if len(causas) > 3:
                    principales = causas[:3]
                    principales.append({
                        "causa": "Otros",
                        "horas": sum(causa["horas"] for causa in causas[3:])
                    })
                else:
                    principales = causas
                maquina["causas"] = [
                    {
                        "causa": causa["causa"],
                        "horas": round(causa["horas"], 2),
                        "impacto_pct": round(causa["horas"] / total_horas * 100, 1)
                        if total_horas > 0 else 0
                    }
                    for causa in principales
                ]
    finally:
        conn.close()

    if not maquinas:
        return {"estado": "vacio", "mes": mes, "maquinas": [], "maquinas_top": []}
    return {
        "estado": "ok",
        "mes": mes,
        "maquinas": maquinas,
        "maquinas_top": maquinas_top
    }

@app.get("/api/graficos/eficiencia-maquinas/")
def grafico_eficiencia_maquinas(mes: str | None = Query(None, description="Mes a mostrar con formato YYYY-MM")):
    if mes is not None:
        try:
            fecha_seleccionada = datetime.strptime(mes, "%Y-%m")
            if fecha_seleccionada.strftime("%Y-%m") != mes:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="El mes debe tener formato YYYY-MM.")

    inicializar_db()
    conn = sqlite3.connect("eficiencia_historia.db")
    try:
        df = pd.read_sql_query("""
            SELECT fecha, puesto_trabajo, hs_programadas, hs_productivas
            FROM historia_detalle_filas
            WHERE fecha IS NOT NULL AND fecha != '' AND puesto_trabajo NOT IN (20, 708)
        """, conn)
        df_708 = pd.read_sql_query("""
            SELECT
                fecha,
                SUM(CASE WHEN concepto = 902 THEN duracion_horas ELSE 0 END) AS horas_codigo_902,
                SUM(duracion_horas) AS horas_totales
            FROM eventos_hphi
            WHERE puesto_trabajo = 708
              AND fecha IS NOT NULL AND fecha != ''
            GROUP BY fecha
        """, conn)
        cursor = conn.cursor()
        cursor.execute("SELECT puesto_trabajo, objetivo_anual FROM metas_maquina")
        objetivos = {int(puesto): objetivo for puesto, objetivo in cursor.fetchall()}
    finally:
        conn.close()

    if df.empty and df_708.empty:
        return {"estado": "vacio", "maquinas": []}

    if not df.empty:
        df["fecha_dt"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["fecha_dt"]).copy()
    else:
        df["fecha_dt"] = pd.Series(dtype="datetime64[ns]")

    if not df_708.empty:
        df_708["fecha_dt"] = pd.to_datetime(df_708["fecha"], errors="coerce")
        df_708 = df_708.dropna(subset=["fecha_dt"]).copy()
    else:
        df_708["fecha_dt"] = pd.Series(dtype="datetime64[ns]")

    if df.empty and df_708.empty:
        return {"estado": "vacio", "maquinas": []}

    if mes is None:
        fechas_maximas = []
        if not df.empty:
            fechas_maximas.append(df["fecha_dt"].max())
        if not df_708.empty:
            fechas_maximas.append(df_708["fecha_dt"].max())
        fecha_seleccionada = max(fechas_maximas).to_pydatetime()
    periodo_seleccionado = pd.Period(fecha_seleccionada, freq="M")
    anio_seleccionado = fecha_seleccionada.year
    numero_mes = fecha_seleccionada.month
    ejercicio_seleccionado_inicio = anio_seleccionado if numero_mes >= 7 else anio_seleccionado - 1

    ejercicios_inicio_disponibles = set()
    if not df.empty:
        df["ejercicio_inicio"] = df["fecha_dt"].apply(
            lambda fecha: fecha.year if fecha.month >= 7 else fecha.year - 1
        )
        ejercicios_inicio_disponibles.update(int(anio) for anio in df["ejercicio_inicio"].unique())
    else:
        df["ejercicio_inicio"] = pd.Series(dtype=int)
    if not df_708.empty:
        df_708["ejercicio_inicio"] = df_708["fecha_dt"].apply(
            lambda fecha: fecha.year if fecha.month >= 7 else fecha.year - 1
        )
        ejercicios_inicio_disponibles.update(int(anio) for anio in df_708["ejercicio_inicio"].unique())
    else:
        df_708["ejercicio_inicio"] = pd.Series(dtype=int)
    ejercicios_inicio = sorted(
        anio for anio in ejercicios_inicio_disponibles
        if anio <= ejercicio_seleccionado_inicio
    )[-4:]
    ejercicios = [
        {
            "ejercicio": f"{inicio % 100:02d}{(inicio + 1) % 100:02d}",
            "inicio": int(inicio)
        }
        for inicio in ejercicios_inicio
    ]

    nombres_meses = [
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
    ]
    dias_mes = periodo_seleccionado.days_in_month
    primer_dia_mes = periodo_seleccionado.start_time
    ultimo_dia_mes = periodo_seleccionado.end_time
    filas_maquinas = []

    puestos_disponibles = set(objetivos) - {708}
    if not df.empty:
        puestos_disponibles.update(df["puesto_trabajo"].dropna().astype(int).unique())
    puestos_disponibles.add(708)

    for puesto in sorted(
        (puesto for puesto in puestos_disponibles if puesto != 708),
        key=lambda p: (
            ORDEN_MAQUINAS_PERSONALIZADO.index(p)
            if p in ORDEN_MAQUINAS_PERSONALIZADO
            else len(ORDEN_MAQUINAS_PERSONALIZADO) + p
        )
    ):
        df_maquina = df[df["puesto_trabajo"] == puesto] if not df.empty else df
        acumulados = []

        for ejercicio in ejercicios:
            seleccion = df_maquina[df_maquina["ejercicio_inicio"] == ejercicio["inicio"]]
            anio_fin_mes = ejercicio["inicio"] if numero_mes >= 7 else ejercicio["inicio"] + 1
            fecha_fin_acumulado = pd.Period(
                year=anio_fin_mes, month=numero_mes, freq="M"
            ).end_time
            seleccion = seleccion[
                (seleccion["fecha_dt"] >= datetime(ejercicio["inicio"], 7, 1))
                & (seleccion["fecha_dt"] <= fecha_fin_acumulado)
            ]

            horas_programadas = seleccion["hs_programadas"].fillna(0).sum()
            horas_productivas = seleccion["hs_productivas"].fillna(0).sum()
            acumulados.append(
                round(horas_productivas / horas_programadas * 100, 2)
                if horas_programadas > 0 else None
            )

        mes_actual = df_maquina[
            (df_maquina["fecha_dt"] >= primer_dia_mes)
            & (df_maquina["fecha_dt"] <= ultimo_dia_mes)
        ]
        diarios_agrupados = mes_actual.groupby(mes_actual["fecha_dt"].dt.day).agg(
            horas_programadas=("hs_programadas", "sum"),
            horas_productivas=("hs_productivas", "sum")
        )
        eficiencia_diaria = []
        for dia in range(1, dias_mes + 1):
            if dia not in diarios_agrupados.index:
                eficiencia_diaria.append(None)
                continue
            horas_programadas = diarios_agrupados.loc[dia, "horas_programadas"]
            horas_productivas = diarios_agrupados.loc[dia, "horas_productivas"]
            eficiencia_diaria.append(
                round(horas_productivas / horas_programadas * 100, 2)
                if horas_programadas > 0 else None
            )

        filas_maquinas.append({
            "puesto": int(puesto),
            "nombre": NOMBRES_MAQUINAS.get(int(puesto), f"Máq {int(puesto)}"),
            "objetivo_anual": objetivos.get(int(puesto)),
            "acumulados": acumulados,
            "eficiencia_diaria": eficiencia_diaria
        })

    if 708 in puestos_disponibles:
        df_maquina_708 = df_708
        acumulados_708 = []

        for ejercicio in ejercicios:
            seleccion = df_maquina_708[
                df_maquina_708["ejercicio_inicio"] == ejercicio["inicio"]
            ]
            anio_fin_mes = ejercicio["inicio"] if numero_mes >= 7 else ejercicio["inicio"] + 1
            fecha_fin_acumulado = pd.Period(
                year=anio_fin_mes, month=numero_mes, freq="M"
            ).end_time
            seleccion = seleccion[
                (seleccion["fecha_dt"] >= datetime(ejercicio["inicio"], 7, 1))
                & (seleccion["fecha_dt"] <= fecha_fin_acumulado)
            ]

            horas_totales = seleccion["horas_totales"].fillna(0).sum()
            horas_codigo_902 = seleccion["horas_codigo_902"].fillna(0).sum()
            acumulados_708.append(
                round(horas_codigo_902 / horas_totales * 100, 2)
                if horas_totales > 0 else None
            )

        registros_mes_708 = df_maquina_708[
            (df_maquina_708["fecha_dt"] >= primer_dia_mes)
            & (df_maquina_708["fecha_dt"] <= ultimo_dia_mes)
        ].copy()
        registros_mes_708["dia"] = registros_mes_708["fecha_dt"].dt.day
        registros_mes_708 = registros_mes_708.set_index("dia")
        eficiencia_diaria_708 = []
        for dia in range(1, dias_mes + 1):
            if dia not in registros_mes_708.index:
                eficiencia_diaria_708.append(None)
                continue
            registro_dia = registros_mes_708.loc[dia]
            horas_totales = registro_dia["horas_totales"]
            horas_codigo_902 = registro_dia["horas_codigo_902"]
            eficiencia_diaria_708.append(
                round(horas_codigo_902 / horas_totales * 100, 2)
                if horas_totales and horas_totales > 0 else None
            )

        filas_maquinas.append({
            "puesto": 708,
            "nombre": NOMBRES_MAQUINAS.get(708, "Máq 708"),
            "objetivo_anual": objetivos.get(708),
            "acumulados": acumulados_708,
            "eficiencia_diaria": eficiencia_diaria_708
        })

        filas_maquinas.sort(key=lambda maquina: (
            ORDEN_MAQUINAS_PERSONALIZADO.index(maquina["puesto"])
            if maquina["puesto"] in ORDEN_MAQUINAS_PERSONALIZADO
            else len(ORDEN_MAQUINAS_PERSONALIZADO) + maquina["puesto"]
        ))

    return {
        "estado": "ok",
        "mes": f"{nombres_meses[numero_mes - 1]} {anio_seleccionado}",
        "mes_seleccionado": periodo_seleccionado.strftime("%Y-%m"),
        "dias_labels": list(range(1, dias_mes + 1)),
        "ejercicios": [ejercicio["ejercicio"] for ejercicio in ejercicios],
        "maquinas": filas_maquinas
    }
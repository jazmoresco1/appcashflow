# app.py - Aplicación principal
import streamlit as st
import pandas as pd
import logging
import time
import traceback
from decimal import Decimal
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from models import (
    init_database, get_db, TipoContacto, Industria, IncotermCompra, 
    IncotermVenta, EstadoOperacion, TipoMovimiento, EstadoPago, TipoPago
)
from database import (
    ContactoService, OperacionService, MovimientoFinancieroService, 
    HSCodeService, FacturaService
)
import logging

# Configuración de página
st.set_page_config(
    page_title="Gestión Comercio Exterior",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar base de datos
init_database()

# Migrar campos nuevos
from database import migrate_database_fields
migrate_database_fields()

# Función para migrar la tabla pagos_programados
def migrate_tipo_pagos():
    """Migra la tabla pagos_programados para agregar y configurar el campo tipo"""
    from sqlalchemy import text
    from models import PagoProgramado
    import streamlit as st
    
    db = next(get_db())
    
    try:
        # Verificar si la columna ya existe
        result = db.execute(text("PRAGMA table_info(pagos_programados)"))
        columns = [row[1] for row in result.fetchall()]
        
        if "tipo" not in columns:
            st.warning("Actualizando estructura de la base de datos...")
            # Agregar la columna tipo
            db.execute(text("ALTER TABLE pagos_programados ADD COLUMN tipo VARCHAR(10)"))
            
            # Actualizar valores basados en la descripción
            pagos = db.query(PagoProgramado).all()
            for pago in pagos:
                if "Depósito" in pago.descripcion or "Compra" in pago.descripcion:
                    db.execute(
                        text(f"UPDATE pagos_programados SET tipo = '{TipoPago.PAGO.value}' WHERE id = {pago.id}")
                    )
                else:  # Cobro o Saldo
                    db.execute(
                        text(f"UPDATE pagos_programados SET tipo = '{TipoPago.COBRO.value}' WHERE id = {pago.id}")
                    )
            
            db.commit()
            st.success("Base de datos actualizada exitosamente.")
            time.sleep(2)
            st.rerun()
    except Exception as e:
        st.error(f"Error actualizando la base de datos: {str(e)}")
        logging.error(f"Error en migración: {str(e)}")

# Configurar logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Funciones de utilidad
@st.cache_data(ttl=1)  # Cache solo por 1 segundo
def load_operaciones():
    """Carga operaciones desde la base de datos"""
    db = next(get_db())
    service = OperacionService(db)
    operaciones = service.obtener_operaciones()
    
    data = []
    for op in operaciones:
        data.append({
            "ID": op.id,
            "Fecha": op.fecha_creacion.strftime("%Y-%m-%d"),
            "Proveedor": op.proveedor.nombre if op.proveedor else "N/A",
            "Cliente": op.cliente.nombre if op.cliente else "N/A",
            "Agente": op.agente_logistico.nombre if op.agente_logistico else "N/A",
            "HS Code": getattr(op.hs_code, 'codigo', 'N/A') if hasattr(op, 'hs_code') and op.hs_code else "N/A",
            "Incoterm Compra": op.incoterm_compra.value,
            "Valor Compra": f"${op.valor_compra:,.2f}",
            "Incoterm Venta": op.incoterm_venta.value,
            "Precio Venta": f"${op.precio_venta:,.2f}",
            "Margen": f"${op.margen_calculado:,.2f}" if op.margen_calculado else "$0.00",
            "Margen %": f"{op.margen_porcentaje:.1f}%" if op.margen_porcentaje else "0.0%",
            "Estado": op.estado.value
        })
    
    return pd.DataFrame(data)

def show_dashboard():
    """Muestra el dashboard principal - ACTUALIZADO"""
    st.header("📊 Dashboard Financiero")
    
    # Filtros de fecha
    st.subheader("📅 Filtros de Período")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        fecha_desde = st.date_input(
            "Desde:",
            value=date.today() - timedelta(days=30),
            help="Fecha de inicio para el análisis"
        )
    
    with col2:
        fecha_hasta = st.date_input(
            "Hasta:",
            value=date.today(),
            help="Fecha de fin para el análisis"
        )
    
    with col3:
        aplicar_filtro = st.button("🔄 Actualizar Dashboard", use_container_width=True)
    
    # Obtener servicios
    db = next(get_db())
    operacion_service = OperacionService(db)
    movimiento_service = MovimientoFinancieroService(db)
    
    # Calcular métricas
    resumen_operaciones = operacion_service.obtener_resumen_margenes(fecha_desde, fecha_hasta)
    saldo_financiero = movimiento_service.calcular_saldo(fecha_hasta)
    
    st.markdown("---")
    
    # Métricas principales - Primera fila
    st.subheader("💰 Resumen Financiero")
    
    # Saldos y Disponibilidad - ACTUALIZADO
    st.write("#### 📊 Saldos y Disponibilidad")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Saldo Actual", 
            f"${saldo_financiero['saldo_actual']:,.2f}",
            help="Saldo real actual (entradas - salidas efectivas)"
        )
        
        st.metric(
            "Saldo Proyectado",
            f"${saldo_financiero['saldo_proyectado']:,.2f}",
            delta=f"${saldo_financiero['saldo_proyectado'] - saldo_financiero['saldo_actual']:,.2f}",
            help="Saldo esperado considerando TODOS los pagos y cobros futuros"
        )
    
    with col2:
        st.metric(
            "Pagos Vencidos",
            f"${saldo_financiero['depositos_pendientes']:,.2f}",
            help=f"Depósitos que ya deberían haberse pagado (hasta {fecha_hasta.strftime('%d/%m/%Y')})"
        )
        
        st.metric(
            "Cobros Vencidos",
            f"${saldo_financiero['cobros_pendientes']:,.2f}",
            help=f"Cobros que ya deberían haber llegado (hasta {fecha_hasta.strftime('%d/%m/%Y')})"
        )
    
    with col3:
        # Mostrar información de pagos futuros si están disponibles
        if 'depositos_futuros' in saldo_financiero:
            st.metric(
                "Pagos Futuros",
                f"${saldo_financiero['depositos_futuros']:,.2f}",
                help="Depósitos programados para fechas futuras"
            )
            
            st.metric(
                "Cobros Futuros",
                f"${saldo_financiero['cobros_futuros']:,.2f}",
                help="Cobros programados para fechas futuras"
            )
    
    # Agregar información adicional sobre el estado financiero
    if saldo_financiero['depositos_pendientes'] > 0 or saldo_financiero['cobros_pendientes'] > 0:
        st.warning(f"""
        ⚠️ **Atención**: Hay pagos/cobros vencidos al {fecha_hasta.strftime('%d/%m/%Y')}:
        - Depósitos vencidos: ${saldo_financiero['depositos_pendientes']:,.2f}
        - Cobros vencidos: ${saldo_financiero['cobros_pendientes']:,.2f}
        
        Ve a "Gestionar Pagos y Cobros" para actualizar el estado.
        """)
    
    # Proyección de Saldos
    st.write("#### 📈 Proyección de Saldos")
    
    # Convertir proyección en DataFrame para gráfico
    proyeccion_data = []
    for fecha_str, valores in saldo_financiero['proyeccion_saldos'].items():
        proyeccion_data.append({
            'Fecha': fecha_str,
            'Saldo Proyectado': valores['saldo'],
            'Ingresos Acumulados': valores['ingresos'],
            'Egresos Acumulados': valores['egresos']
        })
    
    if proyeccion_data:
        df_proyeccion = pd.DataFrame(proyeccion_data)
        df_proyeccion['Fecha'] = pd.to_datetime(df_proyeccion['Fecha'])
        df_proyeccion.sort_values('Fecha', inplace=True)
        
        # Gráfico de líneas para saldo proyectado
        st.line_chart(df_proyeccion.set_index('Fecha')['Saldo Proyectado'])
        
        # Tabla con detalles
        with st.expander("Ver detalles de proyección"):
            df_display = df_proyeccion.copy()
            df_display['Fecha'] = df_display['Fecha'].dt.strftime('%d/%m/%Y')
            df_display['Saldo Proyectado'] = df_display['Saldo Proyectado'].map('${:,.2f}'.format)
            df_display['Ingresos Acumulados'] = df_display['Ingresos Acumulados'].map('${:,.2f}'.format)
            df_display['Egresos Acumulados'] = df_display['Egresos Acumulados'].map('${:,.2f}'.format)
            st.dataframe(df_display, use_container_width=True)
    
    # Movimientos Efectivos
    st.write("#### 💸 Movimientos Efectivos")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Entradas", 
            f"${saldo_financiero['total_entradas']:,.2f}",
            help="Total de ingresos realizados"
        )
    
    with col2:
        st.metric(
            "Total Salidas", 
            f"${saldo_financiero['total_salidas']:,.2f}",
            help="Total de egresos realizados"
        )
    
    with col3:
        st.metric(
            "Depósitos Operaciones", 
            f"${saldo_financiero['depositos_operaciones']:,.2f}",
            help="Total de depósitos realizados por operaciones"
        )
    
    with col4:
        st.metric(
            "Cobros Operaciones", 
            f"${saldo_financiero['cobros_operaciones']:,.2f}",
            help="Total de cobros recibidos por operaciones"
        )
    
    # Métricas de operaciones - Segunda fila
    st.subheader("📈 Métricas de Operaciones")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Operaciones Activas", resumen_operaciones["total_operaciones"])
    
    with col2:
        st.metric("Margen Total", f"${resumen_operaciones['margen_total']:,.2f}")
    
    with col3:
        st.metric("Margen Promedio", f"${resumen_operaciones['margen_promedio']:,.2f}")
    
    with col4:
        st.metric("Margen % Promedio", f"{resumen_operaciones['margen_porcentaje_promedio']:.1f}%")
    
    # Vista de movimientos recientes
    st.markdown("---")
    st.subheader("💸 Movimientos Recientes")
    
    movimientos_recientes = movimiento_service.obtener_movimientos(
        fecha_desde=fecha_desde, 
        fecha_hasta=fecha_hasta
    )
    
    if movimientos_recientes:
        data_movimientos = []
        for mov in movimientos_recientes[:10]:
            data_movimientos.append({
                "Fecha": mov.fecha.strftime("%Y-%m-%d"),
                "Tipo": mov.tipo.value.replace("_", " ").title(),
                "Descripción": mov.descripcion,
                "Entrada": f"${mov.monto_entrada:,.2f}" if mov.monto_entrada > 0 else "-",
                "Salida": f"${mov.monto_salida:,.2f}" if mov.monto_salida > 0 else "-",
                "Referencia": mov.referencia or "-"
            })
        
        df_movimientos = pd.DataFrame(data_movimientos)
        st.dataframe(df_movimientos, use_container_width=True)
    else:
        st.info("No hay movimientos financieros en el período seleccionado.")
    
    # Vista de operaciones recientes
    if resumen_operaciones["total_operaciones"] > 0:
        st.markdown("---")
        st.subheader("📋 Operaciones Recientes")
        df = load_operaciones()
        if not df.empty:
            st.dataframe(df.head(), use_container_width=True)
    else:
        st.info("No hay operaciones registradas en el sistema.")

def show_gestion_financiera():
    """Gestión de movimientos financieros"""
    st.header("💰 Gestión Financiera")
    
    with st.form(key="nuevo_movimiento"):
        col1, col2 = st.columns(2)
        
        with col1:
            fecha_movimiento = st.date_input("Fecha del movimiento:", value=date.today())
            tipo_movimiento = st.selectbox(
                "Tipo de movimiento:",
                options=[
                    TipoMovimiento.APORTE_INICIAL,
                    TipoMovimiento.ADELANTO,
                    TipoMovimiento.RETIRO,
                    TipoMovimiento.DEPOSITO_OPERACION,
                    TipoMovimiento.COBRO_OPERACION,
                    TipoMovimiento.PAGO_IMPUESTOS
                ],
                format_func=lambda x: x.value.replace("_", " ").title()
            )
        
        with col2:
            descripcion = st.text_input(
                "Descripción:",
                placeholder="Ej: Aporte inicial de capital"
            )
            
            referencia = st.text_input(
                "Referencia:",
                placeholder="Ej: Factura #001, Depósito #123"
            )
        
        # Montos
        st.subheader("💵 Montos")
        col1, col2 = st.columns(2)
        
        with col1:
            monto_entrada = st.number_input(
                "Monto Entrada (USD):",
                min_value=0.0,
                value=0.0,
                step=100.0,
                help="Ingresos, cobros, aportes"
            )
        
        with col2:
            monto_salida = st.number_input(
                "Monto Salida (USD):",
                min_value=0.0,
                value=0.0,
                step=100.0,
                help="Egresos, pagos, retiros"
            )
            
        observaciones = st.text_area(
            "Observaciones:",
            placeholder="Información adicional sobre el movimiento"
        )
        
        submitted = st.form_submit_button("💾 Registrar Movimiento", use_container_width=True)
        
        if submitted:
            # VALIDACIONES CORRECTAS PARA MOVIMIENTOS FINANCIEROS
            if not descripcion:
                st.error("La descripción es obligatoria")
            elif monto_entrada == 0 and monto_salida == 0:
                st.error("Debe ingresar al menos un monto (entrada o salida)")
            elif monto_entrada > 0 and monto_salida > 0:
                st.error("Solo puede ingresar entrada O salida, no ambas")
            else:
                try:
                    db = next(get_db())
                    movimiento_service = MovimientoFinancieroService(db)
                    movimiento_service.crear_movimiento(
                        fecha=fecha_movimiento,
                        tipo=tipo_movimiento,
                        descripcion=descripcion,
                        monto_entrada=monto_entrada,
                        monto_salida=monto_salida,
                        referencia=referencia,
                        observaciones=observaciones
                    )
                    st.success("✅ Movimiento registrado exitosamente!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar movimiento: {str(e)}")
                    # Agregar logging para debug
                    logging.error(f"Error en registro de movimiento: {str(e)}")

    # Mostrar resumen de movimientos recientes
    st.markdown("---")
    st.subheader("📊 Movimientos Recientes")
    
    db = next(get_db())
    movimiento_service = MovimientoFinancieroService(db)
    
    # Filtros para ver movimientos
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input(
            "Desde:",
            value=date.today() - timedelta(days=30),
            key="mov_desde"
        )
    with col2:
        fecha_hasta = st.date_input(
            "Hasta:",
            value=date.today(),
            key="mov_hasta"
        )
    
    # Obtener y mostrar movimientos
    movimientos = movimiento_service.obtener_movimientos(fecha_desde, fecha_hasta)
    
    if movimientos:
        data_movimientos = []
        for mov in movimientos:
            data_movimientos.append({
                "Fecha": mov.fecha.strftime("%Y-%m-%d"),
                "Tipo": mov.tipo.value.replace("_", " ").title(),
                "Descripción": mov.descripcion,
                "Entrada": f"${mov.monto_entrada:,.2f}" if mov.monto_entrada > 0 else "-",
                "Salida": f"${mov.monto_salida:,.2f}" if mov.monto_salida > 0 else "-",
                "Referencia": mov.referencia or "-",
                "Observaciones": mov.observaciones or "-"
            })
        
        df_movimientos = pd.DataFrame(data_movimientos)
        st.dataframe(df_movimientos, use_container_width=True)
        
        # Botón para descargar
        csv = df_movimientos.to_csv(index=False)
        st.download_button(
            label="📥 Descargar Movimientos CSV",
            data=csv,
            file_name=f"movimientos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No hay movimientos en el período seleccionado.")
    
    # Mostrar saldo actual
    st.markdown("---")
    st.subheader("💳 Saldo Actual")
    
    saldo = movimiento_service.calcular_saldo(fecha_hasta)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Saldo Actual", f"${saldo['saldo_actual']:,.2f}")
    with col2:
        st.metric("Total Entradas", f"${saldo['total_entradas']:,.2f}")
    with col3:
        st.metric("Total Salidas", f"${saldo['total_salidas']:,.2f}")
    with col4:
        st.metric("Saldo Proyectado", f"${saldo['saldo_proyectado']:,.2f}")
def show_nueva_operacion():
    """Formulario para crear nueva operación"""
    # Initialize session state for payments
    if 'cobros_programados' not in st.session_state:
        st.session_state.cobros_programados = []
    if 'multiple_payments' not in st.session_state:
        st.session_state.multiple_payments = False
    
    st.header("🆕 Nueva Operación")
    
    # Obtener contactos
    db = next(get_db())
    contacto_service = ContactoService(db)
    
    proveedores = contacto_service.obtener_contactos(TipoContacto.PROVEEDOR)
    clientes = contacto_service.obtener_contactos(TipoContacto.CLIENTE)
    agentes = contacto_service.obtener_contactos(TipoContacto.AGENTE_LOGISTICO)
    
    # Verificar que existan contactos
    if not proveedores:
        st.warning("⚠️ No hay proveedores registrados. Ir a 'Gestión de Contactos' primero.")
        return
    
    if not clientes:
        st.warning("⚠️ No hay clientes registrados. Ir a 'Gestión de Contactos' primero.")
        return
    
    # Handle multiple payments configuration BEFORE the form
    st.subheader("💵 Plan de Cobros")
    multiple_payments = st.checkbox(
        "Cliente pagará en varias fechas", 
        value=st.session_state.multiple_payments,
        key="multiple_payments_checkbox"
    )
    
    # Update session state
    st.session_state.multiple_payments = multiple_payments
    
    if multiple_payments:
        num_cobros = st.number_input(
            "Número de cobros:", 
            min_value=1, 
            max_value=5, 
            value=2,
            key="num_cobros"
        )
        
        st.write("Distribución de cobros:")
        
        # Create payment schedule
        total_porcentaje = 0
        cobros_temp = []
        
        for i in range(num_cobros):
            with st.container():
                st.write(f"### Cobro #{i+1}")
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    descripcion = st.text_input(
                        f"Descripción cobro #{i+1}:",
                        value=f"Cobro #{i+1}" if i < num_cobros-1 else "Cobro final",
                        key=f"desc_cobro_{i}"
                    )
                with col2:
                    if i < num_cobros - 1:
                        porcentaje = st.number_input(
                            f"% cobro #{i+1}:",
                            min_value=1.0,
                            max_value=99.0,
                            value=50.0 if i == 0 else (100.0 - total_porcentaje) / (num_cobros - i),
                            step=5.0,
                            key=f"pct_cobro_{i}"
                        )
                        total_porcentaje += porcentaje
                    else:
                        porcentaje = 100.0 - total_porcentaje
                        st.write(f"Porcentaje: **{porcentaje:.1f}%**")
                with col3:
                    fecha = st.date_input(
                        f"Fecha cobro #{i+1}:",
                        value=date.today() + timedelta(days=30*(i+1)),
                        key=f"fecha_cobro_{i}"
                    )
                with col4:
                    tipo = st.selectbox(
                        f"Tipo cobro #{i+1}",
                        options=["cobro", "pago"],
                        key=f"tipo_cobro_{i}"
                    )
                cobros_temp.append({
                    "numero": i+1,
                    "descripcion": descripcion,
                    "porcentaje": float(porcentaje),
                    "fecha": fecha,
                    "tipo": tipo
                })
        
        # Show summary and validate
        st.write("### Resumen de cobros programados")
        for cobro in cobros_temp:
            st.write(f"- {cobro['descripcion']}: {cobro['porcentaje']:.1f}% - {cobro['fecha'].strftime('%d/%m/%Y')} - Tipo: {cobro['tipo']}")
        
        # Validate total percentage
        total = sum(c["porcentaje"] for c in cobros_temp)
        if abs(total - 100) > 0.01:
            st.error(f"¡Error! Los porcentajes deben sumar 100%. Actual: {total:.1f}%")
            cobros_temp = []
        else:
            st.session_state.cobros_programados = cobros_temp
    
    # Main operation form
    with st.form("nueva_operacion"):
        st.subheader("📋 Datos Básicos")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            proveedor_seleccionado = st.selectbox(
                "Proveedor:",
                options=proveedores,
                format_func=lambda x: x.nombre
            )
        
        with col2:
            cliente_seleccionado = st.selectbox(
                "Cliente:",
                options=clientes,
                format_func=lambda x: x.nombre
            )
        
        with col3:
            agente_seleccionado = st.selectbox(
                "Agente Logístico:",
                options=[None] + agentes,
                format_func=lambda x: "Sin agente" if x is None else x.nombre
            )
        
        st.subheader("💰 Datos de Compra")
        
        col1, col2 = st.columns(2)
        
        with col1:
            incoterm_compra = st.selectbox(
                "INCOTERM Compra:",
                options=[IncotermCompra.FOB, IncotermCompra.FCA, IncotermCompra.EXW],
                format_func=lambda x: x.value
            )
            
            valor_compra = st.number_input(
                "Valor de Compra (USD):",
                min_value=0.0,
                value=0.0,
                step=100.0
            )
        
        with col2:
            porcentaje_deposito = st.selectbox(
                "% Depósito:",
                options=[30.0, 50.0],
                index=0
            )
            
            porcentaje_custom = st.checkbox("Configurar % manualmente")
            if porcentaje_custom:
                porcentaje_deposito = st.slider("% Depósito personalizado:", 0, 100, 30)
        
        # Fechas
        col1, col2 = st.columns(2)
        with col1:
            fecha_deposito = st.date_input(
                "Fecha de Depósito:",
                value=None
            )
        
        with col2:
            fecha_estimada_saldo = st.date_input(
                "Fecha Estimada Pago Saldo:",
                value=date.today() + timedelta(days=30)
            )
        
        st.subheader("🚛 Costos Adicionales")
        
        col1, col2 = st.columns(2)
        
        with col1:
            costo_flete = st.number_input(
                "Costo de Flete (USD):",
                min_value=0.0,
                value=0.0,
                step=50.0
            )
        
        with col2:
            costo_despachante = st.number_input(
                "Costo Despachante (USD):",
                min_value=0.0,
                value=0.0,
                step=50.0
            )
        
        st.subheader("💸 Datos de Venta")
        
        col1, col2 = st.columns(2)
        
        with col1:
            incoterm_venta = st.selectbox(
                "INCOTERM Venta:",
                options=[IncotermVenta.DAP, IncotermVenta.CIF, IncotermVenta.FOB],
                format_func=lambda x: x.value
            )
        
        with col2:
            precio_venta = st.number_input(
                "Precio de Venta (USD):",
                min_value=0.0,
                value=0.0,
                step=100.0
            )
        
        # Cálculo de margen en tiempo real
        if valor_compra > 0 and precio_venta > 0:
            costo_total = valor_compra + costo_flete + costo_despachante
            margen = precio_venta - costo_total
            margen_porcentaje = (margen / precio_venta) * 100
            
            st.subheader("📈 Resumen Financiero")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Costo Total", f"${costo_total:,.2f}")
            with col2:
                st.metric("Margen", f"${margen:,.2f}")
            with col3:
                st.metric("Margen %", f"{margen_porcentaje:.1f}%")
        
        # Botón de envío
        submitted = st.form_submit_button("💾 Crear Operación", use_container_width=True)
        
        if submitted:
            # VALIDACIONES SIMPLES - SIN VALIDAR PORCENTAJES DE PAGOS
            if valor_compra <= 0:
                st.error("El valor de compra debe ser mayor a 0")
            elif precio_venta <= 0:
                st.error("El precio de venta debe ser mayor a 0")
            elif precio_venta <= valor_compra:
                st.error("El precio de venta debe ser mayor al valor de compra")
            else:
                # Crear operación
                operacion_service = OperacionService(db)
                
                try:
                    # Preparar los pagos programados
                    pagos_programados = []
                    
                    # Siempre agregamos el depósito inicial
                    pagos_programados.append({
                        "numero": 1,
                        "descripcion": "Depósito Inicial",
                        "porcentaje": porcentaje_deposito,
                        "fecha": fecha_deposito,
                        "tipo": "pago"
                    })
                    
                    # Agregamos el saldo de pago (la diferencia)
                    pagos_programados.append({
                        "numero": 2,
                        "descripcion": "Saldo Compra",
                        "porcentaje": 100 - porcentaje_deposito,
                        "fecha": fecha_estimada_saldo,
                        "tipo": "pago"
                    })
                    
                    # Si hay cobros múltiples programados, los agregamos
                    if st.session_state.multiple_payments and st.session_state.cobros_programados:
                        for cobro in st.session_state.cobros_programados:
                            num = len(pagos_programados) + 1
                            pagos_programados.append({
                                "numero": num,
                                "descripcion": cobro["descripcion"],
                                "porcentaje": cobro["porcentaje"],
                                "fecha": cobro["fecha"],
                                "tipo": "cobro"
                            })
                
                    operacion = operacion_service.crear_operacion(
                        proveedor_id=proveedor_seleccionado.id,
                        cliente_id=cliente_seleccionado.id,
                        agente_logistico_id=agente_seleccionado.id if agente_seleccionado else None,
                        incoterm_compra=incoterm_compra,
                        valor_compra=valor_compra,
                        incoterm_venta=incoterm_venta,
                        precio_venta=precio_venta,
                        costo_flete=costo_flete,
                        costo_despachante=costo_despachante,
                        pagos_programados=pagos_programados
                    )
                    
                    # Clear session state after successful creation
                    st.session_state.cobros_programados = []
                    st.session_state.multiple_payments = False
                    
                    st.success(f"✅ Operación #{operacion.id} creada exitosamente!")
                    st.balloons()
                    
                    # Mostrar resumen de la operación creada
                    st.info(f"""
                    **Resumen de la Operación:**
                    - Proveedor: {proveedor_seleccionado.nombre}
                    - Cliente: {cliente_seleccionado.nombre}
                    - Valor Compra: ${valor_compra:,.2f}
                    - Precio Venta: ${precio_venta:,.2f}
                    - Margen: ${operacion.margen_calculado:,.2f} ({operacion.margen_porcentaje:.1f}%)
                    """)
                    
                    # Limpiar cache para actualizar la vista
                    st.cache_data.clear()
                    
                except Exception as e:
                    st.error(f"Error al crear operación: {str(e)}")
                    st.error(f"Detalles del error: {traceback.format_exc()}")
def show_operaciones():
    """Muestra todas las operaciones"""
    st.header("📋 Lista de Operaciones")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        estado_filtro = st.selectbox(
            "Filtrar por estado:",
            options=["Todos", "ACTIVA", "COMPLETADA", "CANCELADA"]
        )
    
    # Cargar y mostrar datos
    df = load_operaciones()
    st.cache_data.clear()  # Limpiar caché antes de mostrar
    
    if df is not None and not df.empty:
        if estado_filtro != "Todos":
            df = df[df["Estado"] == estado_filtro.lower()]
        
        st.dataframe(df, use_container_width=True)
        
        # Botón para descargar CSV
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Descargar CSV",
            data=csv,
            file_name=f"operaciones_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        # Mostrar detalle de pagos programados
        if not df.empty:
            st.subheader("💸 Pagos Programados por Operación")
            
            operacion_id = st.selectbox(
                "Ver pagos de operación:",
                options=df["ID"].tolist(),
                format_func=lambda x: f"Op #{x} - {df[df['ID']==x]['Cliente'].iloc[0] if len(df[df['ID']==x]) > 0 else 'N/A'}"
            )
            
            if operacion_id:
                # Obtener pagos programados
                from models import PagoProgramado
                db = next(get_db())
                pagos = db.query(PagoProgramado).filter(PagoProgramado.operacion_id == operacion_id).all()
                
                if pagos:
                    data_pagos = []
                    for pago in pagos:
                        data_pagos.append({
                            "Pago #": pago.numero_pago,
                            "Descripción": pago.descripcion,
                            "Porcentaje": f"{pago.porcentaje}%",
                            "Fecha Programada": pago.fecha_programada.strftime("%Y-%m-%d"),
                            "Fecha Real": pago.fecha_real_pago.strftime("%Y-%m-%d") if pago.fecha_real_pago else "Pendiente",
                            "Estado": pago.estado.value.title()
                        })
                    
                    df_pagos = pd.DataFrame(data_pagos)
                    st.dataframe(df_pagos, use_container_width=True)
                else:
                    st.info("Esta operación no tiene pagos programados.")
    else:
        st.info("No hay operaciones registradas.")

def show_contactos():
    """Gestión de contactos"""
    st.header("👥 Gestión de Contactos")
    
    db = next(get_db())
    contacto_service = ContactoService(db)
    
    tab1, tab2 = st.tabs(["Ver Contactos", "Nuevo Contacto"])
    
    with tab1:
        tipo_filtro = st.selectbox(
            "Filtrar por tipo:",
            options=["Todos", "PROVEEDOR", "CLIENTE", "AGENTE_LOGISTICO"]
        )
        
        if tipo_filtro == "Todos":
            contactos = contacto_service.obtener_contactos()
        else:
            contactos = contacto_service.obtener_contactos(TipoContacto(tipo_filtro.lower()))
        
        if contactos:
            data = []
            for contacto in contactos:
                data.append({
                    "ID": contacto.id,
                    "Nombre": contacto.nombre,
                    "Razón Social": getattr(contacto, 'razon_social', None) or "N/A",
                    "Tipo": contacto.tipo.value.title(),
                    "País": contacto.pais or "N/A",
                    "Provincia": getattr(contacto, 'provincia', None) or "N/A",
                    "Email": contacto.email or "N/A",
                    "Teléfono": contacto.telefono or "N/A",
                    "ID Fiscal": getattr(contacto, 'numero_identificacion_fiscal', None) or "N/A",
                    "Industria": getattr(contacto, 'industria', None).value.title() if getattr(contacto, 'industria', None) else "N/A",
                    "Dir. Fábrica": getattr(contacto, 'direccion_fabrica', None) or "N/A",
                    "Puerto": getattr(contacto, 'puerto_conveniente', None) or "N/A"
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay contactos registrados.")
    
    with tab2:
        with st.form("nuevo_contacto"):
            st.subheader("Información Básica")
            
            col1, col2 = st.columns(2)
            
            with col1:
                nombre = st.text_input("Nombre:", placeholder="Ej: Proveedor ABC")
                tipo = st.selectbox(
                    "Tipo:",
                    options=[TipoContacto.PROVEEDOR, TipoContacto.CLIENTE, TipoContacto.AGENTE_LOGISTICO],
                    format_func=lambda x: x.value.replace("_", " ").title()
                )
            
            with col2:
                razon_social = st.text_input("Razón Social:", placeholder="Razón social completa")
                pais = st.text_input("País:", placeholder="Ej: China, Argentina")
            
            # Campo de provincia
            provincia = st.text_input("Provincia/Estado:", placeholder="Ej: Buenos Aires, Guangdong")
            
            # Campo de industria para clientes
            industria = None
            if tipo == TipoContacto.CLIENTE:
                industria = st.selectbox(
                    "Industria:",
                    options=list(Industria),
                    format_func=lambda x: x.value.replace("_", " ").title(),
                    help="Seleccione la industria principal del cliente"
                )
            
            # Campos adicionales para proveedores
            direccion_fabrica = None
            puerto_conveniente = None
            if tipo == TipoContacto.PROVEEDOR:
                direccion_fabrica = st.text_area(
                    "Dirección de la Fábrica:",
                    placeholder="Dirección completa de la planta de producción"
                )
                puerto_conveniente = st.text_input(
                    "Puerto Conveniente/Cercano:",
                    placeholder="Ej: Puerto de Shanghai, Puerto de Shenzhen"
                )
            
            st.subheader("Información de Contacto")
            
            col1, col2 = st.columns(2)
            
            with col1:
                email = st.text_input("Email:", placeholder="contacto@empresa.com")
                telefono = st.text_input("Teléfono:", placeholder="+86 123 456 7890")
            
            with col2:
                numero_identificacion_fiscal = st.text_input(
                    "Número de Identificación Fiscal:", 
                    placeholder="CUIT, EIN, RUT, etc.",
                    help="Ingrese el número de identificación fiscal según el país"
                )
            
            st.subheader("Dirección Fiscal")
            direccion_fiscal = st.text_area(
                "Dirección Fiscal:",
                placeholder="Dirección completa para facturación"
            )
            
            submitted = st.form_submit_button("➕ Crear Contacto", use_container_width=True)
            
            if submitted:
                if not nombre:
                    st.error("El nombre es obligatorio")
                else:
                        try:
                            contacto_service.crear_contacto(
                                nombre=nombre,
                                tipo=tipo,
                                pais=pais,
                                provincia=provincia,
                                email=email,
                                telefono=telefono,
                                razon_social=razon_social,
                                direccion_fiscal=direccion_fiscal,
                                numero_identificacion_fiscal=numero_identificacion_fiscal,
                                industria=industria,
                                direccion_fabrica=direccion_fabrica,
                                puerto_conveniente=puerto_conveniente
                            )
                            st.success("✅ Contacto creado exitosamente!")
                            st.balloons()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al crear contacto: {str(e)}")

def show_hs_codes():
    """Gestión de códigos HS e impuestos"""
    st.header("📦 Gestión de Códigos HS")
    
    db = next(get_db())
    hs_service = HSCodeService(db)
    
    tab1, tab2 = st.tabs(["Ver Códigos HS", "Nuevo Código HS"])
    
    with tab1:
        st.subheader("Códigos HS Registrados")
        
        hs_codes = hs_service.obtener_hs_codes()
        
        if hs_codes:
            for hs in hs_codes:
                with st.expander(f"**{hs.codigo}** - {hs.descripcion}"):
                    impuestos = hs_service.obtener_impuestos_por_hs(hs.id)
                    
                    if impuestos:
                        st.write("**Impuestos asociados:**")
                        for imp in impuestos:
                            st.write(f"- {imp.nombre}: {imp.porcentaje}%")
                    else:
                        st.write("Sin impuestos asociados")
        else:
            st.info("No hay códigos HS registrados")
    
    with tab2:
        st.subheader("Registrar Nuevo Código HS")
        
        with st.form("nuevo_hs"):
            codigo = st.text_input("Código HS:", placeholder="Ej: 8471.30.00")
            descripcion = st.text_area("Descripción:", placeholder="Descripción del producto")
            
            st.subheader("Impuestos Asociados")
            num_impuestos = st.number_input("Cantidad de impuestos:", min_value=0, max_value=10, value=1)
            
            impuestos = []
            for i in range(int(num_impuestos)):
                st.write(f"**Impuesto {i+1}**")
                col1, col2 = st.columns(2)
                
                with col1:
                    nombre_imp = st.text_input(f"Nombre {i+1}:", placeholder="Ej: Derechos de Importación", key=f"imp_nombre_{i}")
                with col2:
                    porcentaje_imp = st.number_input(f"Porcentaje {i+1}:", min_value=0.0, max_value=100.0, value=0.0, key=f"imp_pct_{i}")
                
                if nombre_imp and porcentaje_imp > 0:
                    impuestos.append({
                        'nombre': nombre_imp,
                        'porcentaje': porcentaje_imp
                    })
            
            submitted = st.form_submit_button("💾 Registrar Código HS")
            
            if submitted:
                if not codigo:
                    st.error("El código HS es obligatorio")
                else:
                        try:
                            hs_service.crear_hs_code(
                                codigo=codigo,
                                descripcion=descripcion,
                                impuestos=impuestos
                            )
                            st.success("✅ Código HS registrado exitosamente!")
                            st.balloons()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al registrar código HS: {str(e)}")

def show_facturas():
    """Gestión de facturas"""
    st.header("📄 Gestión de Facturas")
    
    db = next(get_db())
    factura_service = FacturaService(db)
    operacion_service = OperacionService(db)
    
    tab1, tab2 = st.tabs(["Ver Facturas", "Generar Factura"])
    
    with tab1:
        st.subheader("Facturas Generadas")
        
        facturas = factura_service.obtener_facturas()
        
        if facturas:
            data = []
            for factura in facturas:
                data.append({
                    "Número": factura.numero,
                    "Fecha": factura.fecha.strftime("%Y-%m-%d"),
                    "Cliente": factura.operacion.cliente.nombre,
                    "Subtotal FOB": f"${factura.subtotal_fob:,.2f}",
                    "Total INCOTERM": f"${factura.total_incoterm:,.2f}",
                    "Moneda": factura.moneda,
                    "Operación ID": factura.operacion_id
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay facturas generadas")
    
    with tab2:
        st.subheader("Generar Nueva Factura")
        
        # Obtener operaciones activas
        operaciones = operacion_service.obtener_operaciones(EstadoOperacion.ACTIVA)
        
        if not operaciones:
            st.warning("No hay operaciones activas para facturar")
            return
        
        with st.form("generar_factura"):
            operacion_seleccionada = st.selectbox(
                "Seleccionar Operación:",
                options=operaciones,
                format_func=lambda x: f"Op #{x.id} - {x.cliente.nombre} - ${x.precio_venta:,.2f}"
            )
            
            st.markdown("---")
            st.subheader("📋 Datos de la Factura (Editables)")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Datos básicos de la factura
                numero_factura = st.text_input(
                    "Número de Factura:",
                    value=f"FAC-{datetime.now().strftime('%Y%m%d')}-{operacion_seleccionada.id if operacion_seleccionada else '001'}",
                    help="Ingrese el número de factura personalizado"
                )
                
                fecha_factura = st.date_input(
                    "Fecha de Factura:",
                    value=date.today(),
                    help="Debe ser anterior a la fecha HBL"
                )
                
                moneda = st.selectbox(
                    "Moneda:",
                    options=["USD", "EUR", "ARS", "CNY"],
                    index=0
                )
            
            with col2:
                # Montos editables
                if operacion_seleccionada:
                    subtotal_fob = st.number_input(
                        "Subtotal FOB:",
                        value=float(operacion_seleccionada.valor_compra),
                        min_value=0.0,
                        step=0.01,
                        format="%.2f"
                    )
                    
                    total_incoterm = st.number_input(
                        f"Total {operacion_seleccionada.incoterm_venta.value if operacion_seleccionada else 'INCOTERM'}:",
                        value=float(operacion_seleccionada.precio_venta),
                        min_value=0.0,
                        step=0.01,
                        format="%.2f"
                    )
                else:
                    subtotal_fob = st.number_input(
                        "Subtotal FOB:",
                        value=0.0,
                        min_value=0.0,
                        step=0.01,
                        format="%.2f"
                    )
                    
                    total_incoterm = st.number_input(
                        "Total INCOTERM:",
                        value=0.0,
                        min_value=0.0,
                        step=0.01,
                        format="%.2f"
                    )
            
            # Descripción personalizable
            descripcion_productos = st.text_area(
                "Descripción de Productos/Servicios:",
                value=operacion_seleccionada.descripcion_venta if operacion_seleccionada and operacion_seleccionada.descripcion_venta else "",
                placeholder="Describa los productos o servicios facturados",
                height=100
            )
            
            # Observaciones adicionales
            observaciones_factura = st.text_area(
                "Observaciones de la Factura:",
                placeholder="Observaciones adicionales para la factura (términos de pago, etc.)",
                height=80
            )
            
            # Mostrar información del cliente seleccionado
            if operacion_seleccionada:
                st.markdown("---")
                st.subheader("👤 Información del Cliente")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    cliente = operacion_seleccionada.cliente
                    st.write(f"**Nombre:** {cliente.nombre}")
                    if hasattr(cliente, 'razon_social') and cliente.razon_social:
                        st.write(f"**Razón Social:** {cliente.razon_social}")
                    if hasattr(cliente, 'numero_identificacion_fiscal') and cliente.numero_identificacion_fiscal:
                        st.write(f"**ID Fiscal:** {cliente.numero_identificacion_fiscal}")
                
                with col2:
                    if hasattr(cliente, 'direccion_fiscal') and cliente.direccion_fiscal:
                        st.write(f"**Dirección:** {cliente.direccion_fiscal}")
                    if hasattr(cliente, 'pais') and cliente.pais:
                        st.write(f"**País:** {cliente.pais}")
                    if hasattr(cliente, 'provincia') and cliente.provincia:
                        st.write(f"**Provincia:** {cliente.provincia}")
                
                # Validación de fecha HBL
                if hasattr(operacion_seleccionada, 'fecha_hbl') and operacion_seleccionada.fecha_hbl and fecha_factura >= operacion_seleccionada.fecha_hbl:
                    st.error(f"⚠️ La fecha de factura debe ser anterior al HBL ({operacion_seleccionada.fecha_hbl})")
            
            submitted = st.form_submit_button("📄 Generar Factura", use_container_width=True)
            
            if submitted:
                if not numero_factura:
                    st.error("El número de factura es obligatorio")
                elif not descripcion_productos:
                    st.error("La descripción de productos es obligatoria")
                else:
                    try:
                        # Crear factura con datos personalizados
                        factura_service.generar_factura_personalizada(
                            operacion_id=operacion_seleccionada.id,
                            numero=numero_factura,
                            fecha_factura=fecha_factura,
                            subtotal_fob=subtotal_fob,
                            total_incoterm=total_incoterm,
                            moneda=moneda,
                            descripcion=descripcion_productos,
                            observaciones=observaciones_factura
                        )
                        st.success("✅ Factura generada exitosamente!")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al generar factura: {str(e)}")

def main():
    # Ejecutar migración si es necesario
    migrate_tipo_pagos()
    
    st.title("🌍 Gestión de Comercio Exterior")
    st.markdown("---")
    
    # Sidebar para navegación
    st.sidebar.title("Navegación")
    page = st.sidebar.selectbox(
        "Seleccionar página:",
        [
            "Dashboard", 
            "Nueva Operación", 
            "Ver Operaciones", 
            "Gestión Financiera", 
            "Gestionar Pagos y Cobros",
            "Gestión de Contactos",
            "Códigos HS",
            "Facturas",
            "Cargar desde Excel",
            "Borrar Registros"
        ]
    )
    
    if page == "Dashboard":
        show_dashboard()
    elif page == "Nueva Operación":
        show_nueva_operacion()
    elif page == "Ver Operaciones":
        show_operaciones()
    elif page == "Gestión Financiera":
        show_gestion_financiera()
    elif page == "Gestionar Pagos y Cobros":
        show_gestionar_pagos()
    elif page == "Gestión de Contactos":
        show_contactos()
    elif page == "Códigos HS":
        show_hs_codes()
    elif page == "Facturas":
        show_facturas()
    elif page == "Cargar desde Excel":
        show_cargar_excel()
    elif page == "Borrar Registros":
        show_borrar_registros()

def show_gestionar_pagos():
    """Gestionar pagos y cobros pendientes"""
    st.header("💸 Gestionar Pagos y Cobros")
    
    db = next(get_db())
    operacion_service = OperacionService(db)
    movimiento_service = MovimientoFinancieroService(db)
    
    # Inicializar variables para evitar errores
    depositos = []
    cobros = []
    
    # Obtener todas las operaciones activas
    operaciones = operacion_service.obtener_operaciones(EstadoOperacion.ACTIVA)
    
    if not operaciones:
        st.info("No hay operaciones activas para gestionar pagos")
        return
    
    # Usar solo los IDs para selección
    operaciones_ids = [(op.id, f"#{op.id} - {op.cliente.nombre} (${op.precio_venta:,.2f})") for op in operaciones]
    
    # Selector de operación
    operacion_id_seleccionado = st.selectbox(
        "Seleccionar Operación:",
        options=[id_op for id_op, _ in operaciones_ids],
        format_func=lambda id_op: next((label for id, label in operaciones_ids if id == id_op), "")
    )
    
    if operacion_id_seleccionado:
        # Obtener la operación fresca de la base de datos
        operacion_seleccionada = next((op for op in operaciones if op.id == operacion_id_seleccionado), None)
        
        if operacion_seleccionada:
            st.write(f"**Operación #{operacion_seleccionada.id}**")
            st.write(f"Proveedor: {operacion_seleccionada.proveedor.nombre}")
            st.write(f"Cliente: {operacion_seleccionada.cliente.nombre}")
            st.write(f"Valor compra: ${operacion_seleccionada.valor_compra:,.2f}")
            st.write(f"Precio venta: ${operacion_seleccionada.precio_venta:,.2f}")
            st.write(f"Margen: ${operacion_seleccionada.margen_calculado:,.2f} ({operacion_seleccionada.margen_porcentaje:.1f}%)")
        
            # Obtener los pagos programados de la operación
            from models import PagoProgramado
            pagos = db.query(PagoProgramado).filter(
                PagoProgramado.operacion_id == operacion_seleccionada.id
            ).all()
            
            if pagos:
                # Separar pagos por tipo
                depositos = [p for p in pagos if p.tipo == TipoPago.PAGO]
                cobros = [p for p in pagos if p.tipo == TipoPago.COBRO]
                
                # Mostrar depósitos
                if depositos:
                    st.subheader("📤 Depósitos y Pagos")
                    for pago in depositos:
                        with st.container(border=True):
                            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                            
                            # Calcular monto
                            costo_total = operacion_seleccionada.valor_compra + operacion_seleccionada.costo_flete + operacion_seleccionada.costo_despachante
                            monto = costo_total * pago.porcentaje / 100
                            
                            with col1:
                                st.write(f"**{pago.descripcion}** ({pago.porcentaje:.1f}%)")
                                st.caption(f"ID: {pago.id}")
                        
                        with col2:
                            st.write(f"Monto: **${monto:,.2f}**")
                            st.caption(f"Programado: {pago.fecha_programada.strftime('%d/%m/%Y')}")
                        
                        with col3:
                            estado_color = "green" if pago.estado == EstadoPago.PAGADO else "orange" if pago.estado == EstadoPago.PENDIENTE else "red"
                            st.markdown(f"Estado: <span style='color:{estado_color};font-weight:bold'>{pago.estado.value.upper()}</span>", unsafe_allow_html=True)
                            if pago.fecha_real_pago:
                                st.caption(f"Pagado: {pago.fecha_real_pago.strftime('%d/%m/%Y')}")
                        
                        with col4:
                            # Solo mostrar botón para cambiar estado si está pendiente
                            if pago.estado == EstadoPago.PENDIENTE:
                                # Formulario pequeño para seleccionar fecha
                                with st.form(key=f"form_pagar_{pago.id}"):
                                    fecha_real_pago = st.date_input(
                                        "Fecha real:",
                                        value=date.today(),
                                        key=f"fecha_pago_{pago.id}",
                                        help="Seleccione la fecha real del pago"
                                    )
                                    if st.form_submit_button("Pagar", use_container_width=True):
                                        # Registrar el movimiento y cambiar el estado
                                        try:
                                            # Crear movimiento financiero
                                            movimiento_service.crear_movimiento(
                                                fecha=fecha_real_pago,
                                                tipo=TipoMovimiento.DEPOSITO_OPERACION,
                                                descripcion=f"Pago: {pago.descripcion} - Op #{operacion_seleccionada.id}",
                                                monto_salida=monto,
                                                operacion_id=operacion_seleccionada.id
                                            )
                                            
                                            # Actualizar estado del pago - obtener de la BD para evitar detached
                                            pago_update = db.query(PagoProgramado).filter(PagoProgramado.id == pago.id).first()
                                            if pago_update:
                                                pago_update.estado = EstadoPago.PAGADO
                                                pago_update.fecha_real_pago = fecha_real_pago
                                                db.commit()
                                                
                                                st.success(f"Pago registrado exitosamente")
                                                time.sleep(1)
                                                st.rerun()
                                            else:
                                                st.error("No se pudo encontrar el pago en la base de datos")
                                        except Exception as e:
                                            st.error(f"Error al registrar pago: {str(e)}")
            
            # Mostrar cobros
            if cobros:
                st.subheader("📥 Cobros")
                for cobro in cobros:
                    with st.container(border=True):
                        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                        
                        # Calcular monto
                        monto = operacion_seleccionada.precio_venta * cobro.porcentaje / 100
                        
                        with col1:
                            st.write(f"**{cobro.descripcion}** ({cobro.porcentaje:.1f}%)")
                            st.caption(f"ID: {cobro.id}")
                        
                        with col2:
                            st.write(f"Monto: **${monto:,.2f}**")
                            st.caption(f"Programado: {cobro.fecha_programada.strftime('%d/%m/%Y')}")
                        
                        with col3:
                            estado_color = "green" if cobro.estado == EstadoPago.PAGADO else "orange" if cobro.estado == EstadoPago.PENDIENTE else "red"
                            st.markdown(f"Estado: <span style='color:{estado_color};font-weight:bold'>{cobro.estado.value.upper()}</span>", unsafe_allow_html=True)
                            if cobro.fecha_real_pago:
                                st.caption(f"Cobrado: {cobro.fecha_real_pago.strftime('%d/%m/%Y')}")
                        
                        with col4:
                            # Solo mostrar botón para cambiar estado si está pendiente
                            if cobro.estado == EstadoPago.PENDIENTE:
                                # Formulario pequeño para seleccionar fecha
                                with st.form(key=f"form_cobrar_{cobro.id}"):
                                    fecha_real_cobro = st.date_input(
                                        "Fecha real:",
                                        value=date.today(),
                                        key=f"fecha_cobro_{cobro.id}",
                                        help="Seleccione la fecha real del cobro"
                                    )
                                    if st.form_submit_button("Cobrar", use_container_width=True):
                                        # Registrar el movimiento y cambiar el estado
                                        try:
                                            # Crear movimiento financiero
                                            movimiento_service.crear_movimiento(
                                                fecha=fecha_real_cobro,
                                                tipo=TipoMovimiento.COBRO_OPERACION,
                                                descripcion=f"Cobro: {cobro.descripcion} - Op #{operacion_seleccionada.id}",
                                                monto_entrada=monto,
                                                operacion_id=operacion_seleccionada.id
                                            )
                                            
                                            # Actualizar estado del cobro - obtener de la BD para evitar detached
                                            cobro_update = db.query(PagoProgramado).filter(PagoProgramado.id == cobro.id).first()
                                            if cobro_update:
                                                cobro_update.estado = EstadoPago.PAGADO
                                                cobro_update.fecha_real_pago = fecha_real_cobro
                                                db.commit()
                                                
                                                st.success(f"Cobro registrado exitosamente")
                                                time.sleep(1)
                                                st.rerun()
                                            else:
                                                st.error("No se pudo encontrar el cobro en la base de datos")
                                        except Exception as e:
                                            st.error(f"Error al registrar cobro: {str(e)}")
        else:
            st.info("No hay pagos programados para esta operación")

def show_cargar_excel():
    """Carga movimientos desde archivo Excel"""
    st.header("📂 Cargar Movimientos desde Excel")
    
    # Mostrar formato esperado
    st.subheader("📋 Formato Esperado del Excel")
    
    # Crear DataFrame de ejemplo para mostrar el formato
    ejemplo_data = {
        "Factura": ["FAC-001", "FAC-002"],
        "Fecha": ["2025-01-15", "2025-01-20"],
        "Proveedor": ["Proveedor ABC", "Proveedor XYZ"],
        "Codigo_Producto": ["PROD001", "PROD002"],
        "Cliente": ["Cliente 123", "Cliente 456"],
        "INCOTERM": ["FOB", "CIF"],
        "Origen": ["China", "Brasil"],
        "Puerto_Origen": ["Shanghai", "Santos"],
        "Destino_Final": ["Buenos Aires", "Montevideo"],
        "Valor_Compra_FOB": [1000.00, 1500.00],
        "Porcentaje_Deposito": [30, 50],
        "Fecha_Deposito": ["2025-01-10", "2025-01-15"],
        "Fecha_Pago_Saldo": ["2025-02-15", "2025-02-20"],
        "Valor_Venta": [1200.00, 1800.00],
        "Numero_Cuotas": [2, 3],
        "Fechas_Cuotas": ["2025-02-15;2025-03-15", "2025-02-20;2025-03-20;2025-04-20"],
        "Observaciones": ["Entrega urgente", "Cliente premium"]
    }
    
    df_ejemplo = pd.DataFrame(ejemplo_data)
    st.dataframe(df_ejemplo, use_container_width=True)
    
    # Información sobre el formato
    st.info("""
    **Notas importantes sobre el formato:**
    - Las fechas deben estar en formato YYYY-MM-DD
    - Los valores monetarios deben ser números decimales (usar punto, no coma)
    - Las fechas de cuotas deben separarse con punto y coma (;) si hay varias
    - Los campos obligatorios son: Factura, Fecha, Proveedor, Cliente, Valor_Compra_FOB, Valor_Venta
    - Si no hay cuotas múltiples, dejar Numero_Cuotas = 1 y poner una sola fecha en Fechas_Cuotas
    """)
    
    # Botón para descargar plantilla
    csv_plantilla = df_ejemplo.to_csv(index=False)
    st.download_button(
        label="📥 Descargar Plantilla Excel",
        data=csv_plantilla,
        file_name="plantilla_movimientos.csv",
        mime="text/csv",
        help="Descarga esta plantilla y complétala con tus datos"
    )
    
    st.markdown("---")
    
    # Subida de archivo
    st.subheader("📤 Subir Archivo Excel")
    
    uploaded_file = st.file_uploader(
        "Selecciona tu archivo Excel:",
        type=['xlsx', 'xls', 'csv'],
        help="Formatos soportados: Excel (.xlsx, .xls) y CSV (.csv)"
    )
    
    if uploaded_file is not None:
        try:
            # Leer el archivo según su tipo
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ Archivo cargado exitosamente. {len(df)} filas encontradas.")
            
            # Mostrar preview de los datos
            st.subheader("👀 Vista Previa de Datos")
            st.dataframe(df.head(10), use_container_width=True)
            
            # Validar columnas requeridas
            columnas_requeridas = [
                'Factura', 'Fecha', 'Proveedor', 'Cliente', 
                'Valor_Compra_FOB', 'Valor_Venta'
            ]
            
            columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
            
            if columnas_faltantes:
                st.error(f"❌ Faltan las siguientes columnas obligatorias: {', '.join(columnas_faltantes)}")
                st.info("Por favor, asegúrate de que tu archivo tenga todas las columnas requeridas.")
                return
            
            # Validar que no hay filas vacías en campos obligatorios
            filas_vacias = df[columnas_requeridas].isnull().any(axis=1)
            if filas_vacias.any():
                st.warning(f"⚠️ Hay {filas_vacias.sum()} filas con campos obligatorios vacíos que serán omitidas.")
                df = df[~filas_vacias]
            
            if len(df) == 0:
                st.error("❌ No hay filas válidas para procesar.")
                return
            
            # Botón para procesar
            col1, col2 = st.columns(2)
            
            with col1:
                procesar = st.button(
                    "🚀 Procesar Datos", 
                    type="primary",
                    use_container_width=True,
                    help="Esto creará las operaciones y movimientos en la base de datos"
                )
            
            with col2:
                solo_validar = st.button(
                    "🔍 Solo Validar", 
                    use_container_width=True,
                    help="Validar datos sin crear registros"
                )
            
            if solo_validar or procesar:
                st.subheader("🔍 Validación de Datos")
                
                errores = []
                operaciones_validas = []
                
                db = next(get_db())
                contacto_service = ContactoService(db)
                
                # Obtener contactos existentes para validación
                proveedores_existentes = {p.nombre.lower(): p for p in contacto_service.obtener_contactos(TipoContacto.PROVEEDOR)}
                clientes_existentes = {c.nombre.lower(): c for c in contacto_service.obtener_contactos(TipoContacto.CLIENTE)}
                
                for idx, row in df.iterrows():
                    fila_errores = []
                    row_num = idx + 2  # +2 porque empezamos en fila 2 (después del header)
                    
                    # Validar proveedor existe
                    proveedor_nombre = str(row['Proveedor']).strip().lower()
                    if proveedor_nombre not in proveedores_existentes:
                        fila_errores.append(f"Proveedor '{row['Proveedor']}' no existe en la base de datos")
                    
                    # Validar cliente existe
                    cliente_nombre = str(row['Cliente']).strip().lower()
                    if cliente_nombre not in clientes_existentes:
                        fila_errores.append(f"Cliente '{row['Cliente']}' no existe en la base de datos")
                    
                    # Validar valores numéricos
                    try:
                        valor_compra = float(row['Valor_Compra_FOB'])
                        valor_venta = float(row['Valor_Venta'])
                        
                        if valor_compra <= 0:
                            fila_errores.append("Valor de compra debe ser mayor a 0")
                        if valor_venta <= 0:
                            fila_errores.append("Valor de venta debe ser mayor a 0")
                        if valor_venta <= valor_compra:
                            fila_errores.append("Valor de venta debe ser mayor al valor de compra")
                    except (ValueError, TypeError):
                        fila_errores.append("Valores de compra o venta no son números válidos")
                        valor_compra = 0
                        valor_venta = 0
                    
                    # Validar fechas
                    try:
                        fecha_operacion = pd.to_datetime(row['Fecha']).date()
                    except:
                        fila_errores.append("Fecha no es válida (usar formato YYYY-MM-DD)")
                        fecha_operacion = date.today()
                    
                    if fila_errores:
                        errores.append(f"Fila {row_num}: {'; '.join(fila_errores)}")
                    else:
                        operacion_data = {
                            'fila': row_num,
                            'factura': row['Factura'],
                            'fecha': fecha_operacion,
                            'proveedor': proveedores_existentes[proveedor_nombre],
                            'cliente': clientes_existentes[cliente_nombre],
                            'valor_compra': valor_compra,
                            'valor_venta': valor_venta,
                            'incoterm': row.get('INCOTERM', 'FOB'),
                            'origen': row.get('Origen', ''),
                            'puerto_origen': row.get('Puerto_Origen', ''),
                            'destino_final': row.get('Destino_Final', ''),
                            'porcentaje_deposito': row.get('Porcentaje_Deposito', 30),
                            'fecha_deposito': pd.to_datetime(row['Fecha_Deposito']).date() if pd.notna(row.get('Fecha_Deposito')) else None,
                            'fecha_pago_saldo': pd.to_datetime(row['Fecha_Pago_Saldo']).date() if pd.notna(row.get('Fecha_Pago_Saldo')) else None,
                            'numero_cuotas': int(row.get('Numero_Cuotas', 1)),
                            'fechas_cuotas': str(row.get('Fechas_Cuotas', '')),
                            'observaciones': row.get('Observaciones', '')
                        }
                        operaciones_validas.append(operacion_data)
                
                # Mostrar resultados de validación
                if errores:
                    st.error(f"❌ Se encontraron {len(errores)} errores:")
                    for error in errores[:10]:  # Mostrar solo los primeros 10
                        st.write(f"- {error}")
                    if len(errores) > 10:
                        st.write(f"... y {len(errores) - 10} errores más")
                
                if operaciones_validas:
                    st.success(f"✅ {len(operaciones_validas)} operaciones válidas para procesar")
                    
                    if procesar and not errores:
                        # Procesar las operaciones válidas
                        st.subheader("🚀 Procesando Operaciones")
                        
                        operacion_service = OperacionService(db)
                        operaciones_creadas = 0
                        errores_procesamiento = []
                        
                        progress_bar = st.progress(0)
                        
                        for i, op_data in enumerate(operaciones_validas):
                            try:
                                # Preparar pagos programados
                                pagos_programados = []
                                
                                # Depósito
                                if op_data['fecha_deposito']:
                                    pagos_programados.append({
                                        "numero": 1,
                                        "descripcion": "Depósito Inicial",
                                        "porcentaje": op_data['porcentaje_deposito'],
                                        "fecha": op_data['fecha_deposito'],
                                        "tipo": "pago"
                                    })
                                
                                # Saldo
                                if op_data['fecha_pago_saldo']:
                                    pagos_programados.append({
                                        "numero": 2,
                                        "descripcion": "Saldo Compra",
                                        "porcentaje": 100 - op_data['porcentaje_deposito'],
                                        "fecha": op_data['fecha_pago_saldo'],
                                        "tipo": "pago"
                                    })
                                
                                # Cuotas de cobro
                                if op_data['numero_cuotas'] > 1 and op_data['fechas_cuotas']:
                                    fechas_cuotas = op_data['fechas_cuotas'].split(';')
                                    porcentaje_por_cuota = 100 / op_data['numero_cuotas']
                                    
                                    for j, fecha_cuota_str in enumerate(fechas_cuotas):
                                        try:
                                            fecha_cuota = pd.to_datetime(fecha_cuota_str.strip()).date()
                                            pagos_programados.append({
                                                "numero": len(pagos_programados) + 1,
                                                "descripcion": f"Cobro #{j+1}",
                                                "porcentaje": porcentaje_por_cuota,
                                                "fecha": fecha_cuota,
                                                "tipo": "cobro"
                                            })
                                        except:
                                            continue
                                else:
                                    # Una sola cuota de cobro
                                    fecha_cobro = op_data['fecha_pago_saldo'] or (op_data['fecha_deposito'] + timedelta(days=30) if op_data['fecha_deposito'] else None)
                                    if fecha_cobro:
                                        pagos_programados.append({
                                            "numero": len(pagos_programados) + 1,
                                            "descripcion": "Cobro Total",
                                            "porcentaje": 100,
                                            "fecha": fecha_cobro,
                                            "tipo": "cobro"
                                        })
                                
                                # Crear operación
                                operacion = operacion_service.crear_operacion(
                                    proveedor_id=op_data['proveedor'].id,
                                    cliente_id=op_data['cliente'].id,
                                    incoterm_compra=IncotermCompra.FOB,  # Usar FOB por defecto
                                    valor_compra=op_data['valor_compra'],
                                    incoterm_venta=IncotermVenta.DAP,   # Usar DAP por defecto
                                    precio_venta=op_data['valor_venta'],
                                    pagos_programados=pagos_programados,
                                    observaciones=f"Importado desde Excel - Factura: {op_data['factura']}"
                                )
                                
                                operaciones_creadas += 1
                                
                            except Exception as e:
                                errores_procesamiento.append(f"Fila {op_data['fila']}: {str(e)}")
                            
                            # Actualizar progress bar
                            progress_bar.progress((i + 1) / len(operaciones_validas))
                        
                        st.success(f"✅ Procesamiento completado: {operaciones_creadas} operaciones creadas exitosamente")
                        
                        if errores_procesamiento:
                            st.warning(f"⚠️ {len(errores_procesamiento)} errores durante el procesamiento:")
                            for error in errores_procesamiento[:5]:
                                st.write(f"- {error}")
                        
                        # Limpiar cache
                        st.cache_data.clear()
                        
                        st.balloons()
                    
                    elif procesar and errores:
                        st.error("❌ No se puede procesar debido a errores de validación. Corrige los errores e intenta nuevamente.")
                
        except Exception as e:
            st.error(f"❌ Error al leer el archivo: {str(e)}")
            st.info("Asegúrate de que el archivo esté en el formato correcto y no esté corrupto.")

def show_borrar_registros():
    """Interfaz para borrar registros de diferentes tipos"""
    st.header("🗑️ Borrar Registros")
    
    st.warning("""
    ⚠️ **ADVERTENCIA**: Esta acción es irreversible. 
    
    Asegúrate de hacer una copia de seguridad de tu base de datos antes de borrar registros importantes.
    """)
    
    # Selector de tipo de registro
    tipo_registro = st.selectbox(
        "Tipo de registro a borrar:",
        options=[
            "Operaciones",
            "Movimientos Financieros", 
            "Contactos",
            "Facturas",
            "Códigos HS",
            "Pagos Programados"
        ]
    )
    
    db = next(get_db())
    
    if tipo_registro == "Operaciones":
        show_borrar_operaciones(db)
    elif tipo_registro == "Movimientos Financieros":
        show_borrar_movimientos(db)
    elif tipo_registro == "Contactos":
        show_borrar_contactos(db)
    elif tipo_registro == "Facturas":
        show_borrar_facturas(db)
    elif tipo_registro == "Códigos HS":
        show_borrar_hs_codes(db)
    elif tipo_registro == "Pagos Programados":
        show_borrar_pagos_programados(db)

def show_borrar_operaciones(db):
    """Interfaz para borrar operaciones"""
    st.subheader("🗑️ Borrar Operaciones")
    
    from models import Operacion
    operaciones = db.query(Operacion).order_by(Operacion.fecha_creacion.desc()).all()
    
    if not operaciones:
        st.info("No hay operaciones para borrar.")
        return
    
    # Modo de borrado
    modo = st.radio(
        "Modo de borrado:",
        options=["Individual", "Por Estado", "Todas"],
        horizontal=True
    )
    
    if modo == "Individual":
        # Seleccionar operación específica
        operacion_seleccionada = st.selectbox(
            "Seleccionar operación:",
            options=operaciones,
            format_func=lambda x: f"Op #{x.id} - {x.cliente.nombre} - ${x.precio_venta:,.2f} ({x.estado.value})"
        )
        
        if operacion_seleccionada:
            st.write("**Detalles de la operación:**")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"- ID: {operacion_seleccionada.id}")
                st.write(f"- Fecha: {operacion_seleccionada.fecha_creacion.strftime('%Y-%m-%d')}")
                st.write(f"- Proveedor: {operacion_seleccionada.proveedor.nombre}")
                st.write(f"- Cliente: {operacion_seleccionada.cliente.nombre}")
            
            with col2:
                st.write(f"- Valor Compra: ${operacion_seleccionada.valor_compra:,.2f}")
                st.write(f"- Precio Venta: ${operacion_seleccionada.precio_venta:,.2f}")
                st.write(f"- Estado: {operacion_seleccionada.estado.value}")
                st.write(f"- Margen: ${operacion_seleccionada.margen_calculado:,.2f}")
            
            # Verificar dependencias
            tiene_movimientos = len(operacion_seleccionada.movimientos_financieros) > 0
            tiene_pagos = len(operacion_seleccionada.pagos_programados) > 0
            tiene_facturas = operacion_seleccionada.factura is not None
            
            if tiene_movimientos or tiene_pagos or tiene_facturas:
                st.warning(f"""
                ⚠️ **Esta operación tiene registros relacionados:**
                {f"- {len(operacion_seleccionada.movimientos_financieros)} movimientos financieros" if tiene_movimientos else ""}
                {f"- {len(operacion_seleccionada.pagos_programados)} pagos programados" if tiene_pagos else ""}
                {f"- 1 factura" if tiene_facturas else ""}
                
                Al borrar la operación, también se borrarán todos los registros relacionados.
                """)
            
            confirmar = st.text_input(
                "Para confirmar, escribe 'BORRAR':",
                placeholder="BORRAR"
            )
            
            if st.button("🗑️ Borrar Operación", type="primary"):
                if confirmar == "BORRAR":
                    try:
                        # Borrar registros relacionados primero
                        for movimiento in operacion_seleccionada.movimientos_financieros:
                            db.delete(movimiento)
                        
                        for pago in operacion_seleccionada.pagos_programados:
                            db.delete(pago)
                        
                        if operacion_seleccionada.factura:
                            db.delete(operacion_seleccionada.factura)
                        
                        # Borrar la operación
                        db.delete(operacion_seleccionada)
                        db.commit()
                        
                        st.success("✅ Operación borrada exitosamente")
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error al borrar operación: {str(e)}")
                else:
                    st.error("Debes escribir 'BORRAR' para confirmar")
    
    elif modo == "Por Estado":
        # Borrar por estado
        estado_a_borrar = st.selectbox(
            "Estado de operaciones a borrar:",
            options=[EstadoOperacion.ACTIVA, EstadoOperacion.COMPLETADA, EstadoOperacion.CANCELADA],
            format_func=lambda x: x.value.title()
        )
        
        operaciones_filtradas = [op for op in operaciones if op.estado == estado_a_borrar]
        
        if operaciones_filtradas:
            st.write(f"**Se borrarán {len(operaciones_filtradas)} operaciones con estado '{estado_a_borrar.value}'**")
            
            # Mostrar lista
            for op in operaciones_filtradas[:5]:  # Mostrar solo las primeras 5
                st.write(f"- Op #{op.id}: {op.cliente.nombre} - ${op.precio_venta:,.2f}")
            
            if len(operaciones_filtradas) > 5:
                st.write(f"... y {len(operaciones_filtradas) - 5} más")
            
            confirmar = st.text_input(
                f"Para confirmar, escribe 'BORRAR {len(operaciones_filtradas)} OPERACIONES':",
                placeholder=f"BORRAR {len(operaciones_filtradas)} OPERACIONES"
            )
            
            if st.button("🗑️ Borrar Operaciones por Estado", type="primary"):
                if confirmar == f"BORRAR {len(operaciones_filtradas)} OPERACIONES":
                    try:
                        borradas = 0
                        for operacion in operaciones_filtradas:
                            # Borrar registros relacionados
                            for movimiento in operacion.movimientos_financieros:
                                db.delete(movimiento)
                            for pago in operacion.pagos_programados:
                                db.delete(pago)
                            if operacion.factura:
                                db.delete(operacion.factura)
                        
                            db.delete(operacion)
                            borradas += 1
                        
                        db.commit()
                        st.success(f"✅ {borradas} operaciones borradas exitosamente")
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error al borrar operaciones: {str(e)}")
                else:
                    st.error("Confirmación incorrecta")
        else:
            st.info(f"No hay operaciones con estado '{estado_a_borrar.value}'")
    
    elif modo == "Todas":
        # Borrar todas las operaciones
        st.error("⚠️ **PELIGRO**: Esto borrará TODAS las operaciones y sus registros relacionados")
        
        st.write(f"**Total de operaciones: {len(operaciones)}**")
        
        confirmar1 = st.text_input(
            "Paso 1 - Escribe 'ENTIENDO LOS RIESGOS':",
            placeholder="ENTIENDO LOS RIESGOS"
        )
        
        if confirmar1 == "ENTIENDO LOS RIESGOS":
            confirmar2 = st.text_input(
                f"Paso 2 - Escribe 'BORRAR TODAS LAS {len(operaciones)} OPERACIONES':",
                placeholder=f"BORRAR TODAS LAS {len(operaciones)} OPERACIONES"
            )
            
            if st.button("🗑️ BORRAR TODAS LAS OPERACIONES", type="primary"):
                if confirmar2 == f"BORRAR TODAS LAS {len(operaciones)} OPERACIONES":
                    try:
                        from models import MovimientoFinanciero, PagoProgramado, Factura
                        
                        # Borrar todo en orden
                        db.query(MovimientoFinanciero).delete()
                        db.query(PagoProgramado).delete()
                        db.query(Factura).delete()
                        db.query(Operacion).delete()
                        
                        db.commit()
                        st.success("✅ Todas las operaciones han sido borradas")
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error al borrar todas las operaciones: {str(e)}")
                else:
                    st.error("Confirmación incorrecta")

def show_borrar_movimientos(db):
    """Interfaz para borrar movimientos financieros"""
    st.subheader("🗑️ Borrar Movimientos Financieros")
    
    from models import MovimientoFinanciero
    movimientos = db.query(MovimientoFinanciero).order_by(MovimientoFinanciero.fecha.desc()).all()
    
    if not movimientos:
        st.info("No hay movimientos financieros para borrar.")
        return
    
    # Filtros
    col1, col2 = st.columns(2)
    
    with col1:
        fecha_desde = st.date_input(
            "Desde:",
            value=date.today() - timedelta(days=30)
        )
    
    with col2:
        fecha_hasta = st.date_input(
            "Hasta:",
            value=date.today()
        )
    
    # Filtrar movimientos por fecha
    movimientos_filtrados = [
        m for m in movimientos 
        if fecha_desde <= m.fecha <= fecha_hasta
    ]
    
    if movimientos_filtrados:
        st.write(f"**Movimientos en el período: {len(movimientos_filtrados)}**")
        
        # Mostrar tabla de movimientos
        data_movimientos = []
        for mov in movimientos_filtrados:
            data_movimientos.append({
                "ID": mov.id,
                "Fecha": mov.fecha.strftime("%Y-%m-%d"),
                "Tipo": mov.tipo.value.replace("_", " ").title(),
                "Descripción": mov.descripcion,
                "Entrada": f"${mov.monto_entrada:,.2f}" if mov.monto_entrada > 0 else "-",
                "Salida": f"${mov.monto_salida:,.2f}" if mov.monto_salida > 0 else "-"
            })
        
        df_movimientos = pd.DataFrame(data_movimientos)
        st.dataframe(df_movimientos, use_container_width=True)
        
        # Opciones de borrado
        modo = st.radio(
            "Modo de borrado:",
            options=["Individual", "Por Período"],
            horizontal=True
        )
        
        if modo == "Individual":
            movimiento_id = st.number_input(
                "ID del movimiento a borrar:",
                min_value=1,
                step=1
            )
            
            movimiento_seleccionado = next((m for m in movimientos_filtrados if m.id == movimiento_id), None)
            
            if movimiento_seleccionado:
                st.write("**Detalle del movimiento:**")
                st.write(f"- Fecha: {movimiento_seleccionado.fecha}")
                st.write(f"- Tipo: {movimiento_seleccionado.tipo.value}")
                st.write(f"- Descripción: {movimiento_seleccionado.descripcion}")
                st.write(f"- Entrada: ${movimiento_seleccionado.monto_entrada:,.2f}")
                st.write(f"- Salida: ${movimiento_seleccionado.monto_salida:,.2f}")
                
                if st.button("🗑️ Borrar Movimiento"):
                    try:
                        db.delete(movimiento_seleccionado)
                        db.commit()
                        st.success("✅ Movimiento borrado exitosamente")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error: {str(e)}")
        
        elif modo == "Por Período":
            total_entradas = sum(m.monto_entrada for m in movimientos_filtrados)
            total_salidas = sum(m.monto_salida for m in movimientos_filtrados)
            
            st.write(f"**Resumen del período:**")
            st.write(f"- Total entradas: ${total_entradas:,.2f}")
            st.write(f"- Total salidas: ${total_salidas:,.2f}")
            st.write(f"- Movimientos: {len(movimientos_filtrados)}")
            
            confirmar = st.text_input(
                f"Para borrar {len(movimientos_filtrados)} movimientos, escribe 'BORRAR PERIODO':",
                placeholder="BORRAR PERIODO"
            )
            
            if st.button("🗑️ Borrar Movimientos del Período"):
                if confirmar == "BORRAR PERIODO":
                    try:
                        for mov in movimientos_filtrados:
                            db.delete(mov)
                        db.commit()
                        st.success(f"✅ {len(movimientos_filtrados)} movimientos borrados")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error: {str(e)}")
                else:
                    st.error("Confirmación incorrecta")
    else:
        st.info("No hay movimientos en el período seleccionado.")

def show_borrar_contactos(db):
    """Interfaz para borrar contactos"""
    st.subheader("🗑️ Borrar Contactos")
    
    from models import Contacto
    contactos = db.query(Contacto).order_by(Contacto.nombre).all()
    
    if not contactos:
        st.info("No hay contactos para borrar.")
        return
    
    # Filtro por tipo
    tipo_filtro = st.selectbox(
        "Filtrar por tipo:",
        options=["Todos"] + [tipo.value for tipo in TipoContacto],
        format_func=lambda x: x.title() if x != "Todos" else x
    )
    
    if tipo_filtro != "Todos":
        contactos_filtrados = [c for c in contactos if c.tipo.value == tipo_filtro]
    else:
        contactos_filtrados = contactos
    
    if contactos_filtrados:
        # Verificar dependencias
        contactos_con_operaciones = []
        contactos_sin_operaciones = []
        
        for contacto in contactos_filtrados:
            tiene_operaciones = (
                len(contacto.operaciones_proveedor) > 0 or 
                len(contacto.operaciones_cliente) > 0 or 
                len(contacto.operaciones_agente) > 0
            )
            
            if tiene_operaciones:
                contactos_con_operaciones.append(contacto)
            else:
                contactos_sin_operaciones.append(contacto)
        
        st.write(f"**Contactos encontrados:** {len(contactos_filtrados)}")
        st.write(f"- Sin operaciones asociadas: {len(contactos_sin_operaciones)}")
        st.write(f"- Con operaciones asociadas: {len(contactos_con_operaciones)}")
        
        if contactos_sin_operaciones:
            st.subheader("✅ Contactos sin operaciones (seguros para borrar)")
            
            contactos_seleccionados = st.multiselect(
                "Seleccionar contactos a borrar:",
                options=contactos_sin_operaciones,
                format_func=lambda x: f"{x.nombre} ({x.tipo.value})"
            )
            
            if contactos_seleccionados:
                if st.button("🗑️ Borrar Contactos Seleccionados"):
                    try:
                        for contacto in contactos_seleccionados:
                            db.delete(contacto)
                        db.commit()
                        st.success(f"✅ {len(contactos_seleccionados)} contactos borrados")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error: {str(e)}")
        
        if contactos_con_operaciones:
            st.subheader("⚠️ Contactos con operaciones")
            st.warning("Estos contactos tienen operaciones asociadas. Borrarlos requiere borrar primero las operaciones.")
            
            for contacto in contactos_con_operaciones[:5]:  # Mostrar solo los primeros 5
                total_ops = len(contacto.operaciones_proveedor) + len(contacto.operaciones_cliente) + len(contacto.operaciones_agente)
                st.write(f"- {contacto.nombre}: {total_ops} operaciones")
    else:
        st.info(f"No hay contactos del tipo '{tipo_filtro}'.")

def show_borrar_facturas(db):
    """Interfaz para borrar facturas"""
    st.subheader("🗑️ Borrar Facturas")
    
    from models import Factura
    facturas = db.query(Factura).order_by(Factura.fecha.desc()).all()
    
    if not facturas:
        st.info("No hay facturas para borrar.")
        return
    
    # Mostrar lista de facturas
    data_facturas = []
    for factura in facturas:
        data_facturas.append({
            "ID": factura.id,
            "Número": factura.numero,
            "Fecha": factura.fecha.strftime("%Y-%m-%d"),
            "Cliente": factura.operacion.cliente.nombre,
            "Total": f"${factura.total_incoterm:,.2f}",
            "Op ID": factura.operacion_id
        })
    
    df_facturas = pd.DataFrame(data_facturas)
    st.dataframe(df_facturas, use_container_width=True)
    
    # Seleccionar factura para borrar
    factura_id = st.number_input(
        "ID de la factura a borrar:",
        min_value=1,
        step=1
    )
    
    factura_seleccionada = next((f for f in facturas if f.id == factura_id), None)
    
    if factura_seleccionada:
        st.write("**Detalle de la factura:**")
        st.write(f"- Número: {factura_seleccionada.numero}")
        st.write(f"- Fecha: {factura_seleccionada.fecha}")
        st.write(f"- Cliente: {factura_seleccionada.operacion.cliente.nombre}")
        st.write(f"- Total: ${factura_seleccionada.total_incoterm:,.2f}")
        
        if st.button("🗑️ Borrar Factura"):
            try:
                db.delete(factura_seleccionada)
                db.commit()
                st.success("✅ Factura borrada exitosamente")
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"❌ Error: {str(e)}")

def show_borrar_hs_codes(db):
    """Interfaz para borrar códigos HS"""
    st.subheader("🗑️ Borrar Códigos HS")
    
    from models import HSCode
    hs_codes = db.query(HSCode).order_by(HSCode.codigo).all()
    
    if not hs_codes:
        st.info("No hay códigos HS para borrar.")
        return
    
    # Verificar dependencias
    hs_con_operaciones = []
    hs_sin_operaciones = []
    
    for hs in hs_codes:
        if len(hs.operaciones) > 0:
            hs_con_operaciones.append(hs)
        else:
            hs_sin_operaciones.append(hs)
    
    st.write(f"**Códigos HS encontrados:** {len(hs_codes)}")
    st.write(f"- Sin operaciones: {len(hs_sin_operaciones)}")
    st.write(f"- Con operaciones: {len(hs_con_operaciones)}")
    
    if hs_sin_operaciones:
        st.subheader("✅ Códigos HS sin operaciones")
        
        hs_seleccionados = st.multiselect(
            "Seleccionar códigos a borrar:",
            options=hs_sin_operaciones,
            format_func=lambda x: f"{x.codigo} - {x.descripcion[:50]}..."
        )
        
        if hs_seleccionados:
            if st.button("🗑️ Borrar Códigos HS Seleccionados"):
                try:
                    for hs in hs_seleccionados:
                        # Borrar impuestos asociados primero
                        for impuesto in hs.impuestos:
                            db.delete(impuesto)
                        db.delete(hs)
                    db.commit()
                    st.success(f"✅ {len(hs_seleccionados)} códigos HS borrados")
                    st.rerun()
                except Exception as e:
                    db.rollback()
                    st.error(f"❌ Error: {str(e)}")
    
    if hs_con_operaciones:
        st.subheader("⚠️ Códigos HS con operaciones")
        st.warning("Estos códigos tienen operaciones asociadas.")
        
        for hs in hs_con_operaciones:
            st.write(f"- {hs.codigo}: {len(hs.operaciones)} operaciones")

def show_borrar_pagos_programados(db):
    """Interfaz para borrar pagos programados"""
    st.subheader("🗑️ Borrar Pagos Programados")
    
    from models import PagoProgramado
    pagos = db.query(PagoProgramado).order_by(PagoProgramado.fecha_programada.desc()).all()
    
    if not pagos:
        st.info("No hay pagos programados para borrar.")
        return
    
    # Filtros
    estado_filtro = st.selectbox(
        "Filtrar por estado:",
        options=["Todos"] + [estado.value for estado in EstadoPago],
        format_func=lambda x: x.title() if x != "Todos" else x
    )
    
    if estado_filtro != "Todos":
        pagos_filtrados = [p for p in pagos if p.estado.value == estado_filtro]
    else:
        pagos_filtrados = pagos
    
    if pagos_filtrados:
        # Mostrar tabla
        data_pagos = []
        for pago in pagos_filtrados:
            data_pagos.append({
                "ID": pago.id,
                "Op ID": pago.operacion_id,
                "Descripción": pago.descripcion,
                "Porcentaje": f"{pago.porcentaje}%",
                "Fecha": pago.fecha_programada.strftime("%Y-%m-%d"),
                "Estado": pago.estado.value.title(),
                "Tipo": pago.tipo.value.title() if pago.tipo else "N/A"
            })
        
        df_pagos = pd.DataFrame(data_pagos)
        st.dataframe(df_pagos, use_container_width=True)
        
        # Borrar por estado
        if estado_filtro != "Todos":
            confirmar = st.text_input(
                f"Para borrar {len(pagos_filtrados)} pagos '{estado_filtro}', escribe 'BORRAR {estado_filtro.upper()}':",
                placeholder=f"BORRAR {estado_filtro.upper()}"
            )
            
            if st.button(f"🗑️ Borrar Pagos {estado_filtro.title()}"):
                if confirmar == f"BORRAR {estado_filtro.upper()}":
                    try:
                        for pago in pagos_filtrados:
                            db.delete(pago)
                        db.commit()
                        st.success(f"✅ {len(pagos_filtrados)} pagos borrados")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Error: {str(e)}")
                else:
                    st.error("Confirmación incorrecta")
    else:
        st.info(f"No hay pagos con estado '{estado_filtro}'.")

# database.py - Operaciones de base de datos (CORREGIDO)
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
import logging

# Configurar logging básico si no está configurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
import logging
import logging

class ContactoService:
    """Servicio para gestionar contactos"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def crear_contacto(self, nombre: str, tipo, pais: str = None, 
                      provincia: str = None, email: str = None, telefono: str = None,
                      razon_social: str = None, direccion_fiscal: str = None,
                      numero_identificacion_fiscal: str = None, industria = None,
                      direccion_fabrica: str = None, puerto_conveniente: str = None):
        """Crea un nuevo contacto con campos adicionales para facturación"""
        from models import Contacto
        
        try:
            contacto = Contacto(
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
            self.db.add(contacto)
            self.db.commit()
            self.db.refresh(contacto)
            logging.info(f"Contacto creado: {contacto.id} - {contacto.nombre}")
            return contacto
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error al crear contacto: {str(e)}")
            raise
    
    def obtener_contactos(self, tipo = None):
        """Obtiene todos los contactos o filtra por tipo"""
        from models import Contacto
        
        query = self.db.query(Contacto)
        if tipo:
            query = query.filter(Contacto.tipo == tipo)
        return query.order_by(Contacto.nombre).all()
    
    def obtener_contacto(self, contacto_id: int):
        """Obtiene un contacto por ID"""
        from models import Contacto
        
        return self.db.query(Contacto).filter(Contacto.id == contacto_id).first()

class OperacionService:
    """Servicio para gestionar operaciones"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    def crear_operacion(self, proveedor_id: int, cliente_id: int, 
                       incoterm_compra, valor_compra: float,
                       incoterm_venta, precio_venta: float,
                       agente_logistico_id: int = None,
                       hs_code_id: int = None,
                       pagos_programados: list = None,
                       costo_flete: float = 0.0, 
                       costo_despachante: float = 0.0,
                       origen_bienes: str = None,
                       descripcion_venta: str = None,
                       observaciones: str = None,
                       fecha_hbl: date = None,
                       porcentaje_deposito: float = None,
                       fecha_deposito: date = None,
                       fecha_estimada_pago_saldo: date = None):
        """Crea una nueva operación con todos los campos necesarios"""
        from models import Operacion, PagoProgramado, HSCode, EstadoOperacion, EstadoPago, TipoPago
        
        try:
            self.logger.info("Iniciando creación de operación...")
            
            # Validaciones
            if not proveedor_id or not cliente_id:
                raise ValueError("Proveedor y cliente son obligatorios")
            
            if precio_venta <= valor_compra:
                raise ValueError("El precio de venta debe ser mayor al valor de compra")
            
            if pagos_programados:
                # Primero separamos pagos por tipo usando el campo 'tipo'
                depositos = [p for p in pagos_programados if p.get('tipo') == 'pago']
                cobros = [p for p in pagos_programados if p.get('tipo') == 'cobro']
                
                # Si no hay información de tipo, usamos la descripción como fallback
                if not depositos and not cobros:
                    depositos = [p for p in pagos_programados if "Depósito" in p['descripcion'] or "Compra" in p['descripcion']]
                    cobros = [p for p in pagos_programados if "Cobro" in p['descripcion'] or "Saldo" in p['descripcion']]
                
                # Validamos por separado
                total_depositos = sum(float(pago['porcentaje']) for pago in depositos)
                total_cobros = sum(float(pago['porcentaje']) for pago in cobros) if cobros else 0
                
                # Los depósitos deben sumar 100% del valor de compra
                if abs(total_depositos - 100) > 0.01:
                    self.logger.error(f"Total porcentaje depósitos: {total_depositos}%, pagos: {depositos}")
                    raise ValueError(f"Los porcentajes de depósitos deben sumar 100% (actual: {total_depositos}%)")
                
                # No validamos que los cobros sumen 100% ya que podrían ser parciales

            # Crear operación
            operacion = Operacion(
                proveedor_id=proveedor_id,
                cliente_id=cliente_id,
                agente_logistico_id=agente_logistico_id,
                hs_code_id=hs_code_id,
                incoterm_compra=incoterm_compra,
                valor_compra=valor_compra,
                porcentaje_deposito=porcentaje_deposito,
                fecha_deposito=fecha_deposito,
                fecha_estimada_pago_saldo=fecha_estimada_pago_saldo,
                costo_flete=costo_flete,
                costo_despachante=costo_despachante,
                incoterm_venta=incoterm_venta,
                precio_venta=precio_venta,
                origen_bienes=origen_bienes,
                descripcion_venta=descripcion_venta,
                observaciones=observaciones,
                fecha_hbl=fecha_hbl,
                estado=EstadoOperacion.ACTIVA
            )
            
            self.db.add(operacion)
            self.db.flush()  # Para obtener el ID sin commit
            self.logger.info(f"Operación base creada, ID temporal: {operacion.id}")
            
            # Calcular margen
            operacion.calcular_margen()
            self.logger.info(f"Margen calculado: ${operacion.margen_calculado:,.2f} ({operacion.margen_porcentaje:.1f}%)")
            
            # Crear pagos programados con estado y validar montos
            if pagos_programados:
                costo_total = valor_compra + costo_flete + costo_despachante
                total_depositos = 0
                total_cobros = 0
                
                for pago in pagos_programados:
                    self.logger.info(f"Creando pago programado: {pago['descripcion']} - {pago['porcentaje']}%")
                    
                    # Determinar tipo de pago
                    if 'tipo' in pago and pago['tipo'] == 'cobro':
                        tipo_pago = TipoPago.COBRO
                        monto = precio_venta * pago['porcentaje'] / 100
                        total_cobros += float(pago['porcentaje'])
                    else:
                        tipo_pago = TipoPago.PAGO
                        monto = costo_total * pago['porcentaje'] / 100
                        total_depositos += float(pago['porcentaje'])
                        
                    nuevo_pago = PagoProgramado(
                        operacion_id=operacion.id,
                        numero_pago=pago['numero'],
                        descripcion=pago['descripcion'],
                        porcentaje=pago['porcentaje'],
                        fecha_programada=pago['fecha'],
                        fecha_real_pago=None,
                        estado=EstadoPago.PENDIENTE,
                        tipo=tipo_pago
                    )
                    self.db.add(nuevo_pago)
                
                # Ya validamos los porcentajes al inicio, no necesitamos hacerlo de nuevo
            
            try:
                self.db.commit()
                self.db.refresh(operacion)
                self.logger.info(f"Operación guardada exitosamente con ID: {operacion.id}")
                return operacion
            except Exception as commit_error:
                self.db.rollback()
                self.logger.error(f"Error al guardar la operación: {str(commit_error)}")
                raise commit_error
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error al crear operación: {str(e)}")
            raise
    
    def obtener_operaciones(self, estado = None):
        """Obtiene todas las operaciones o filtra por estado"""
        from models import Operacion
        from sqlalchemy.orm import joinedload
        
        query = self.db.query(Operacion)
        
        # Eager load relationships to avoid detached instance errors
        query = query.options(
            joinedload(Operacion.proveedor),
            joinedload(Operacion.cliente),
            joinedload(Operacion.pagos_programados)
        )
        
        if estado:
            query = query.filter(Operacion.estado == estado)
        return query.order_by(Operacion.fecha_creacion.desc()).all()
    
    def obtener_resumen_margenes(self, fecha_desde: date = None, fecha_hasta: date = None) -> dict:
        """Obtiene un resumen de márgenes por diferentes criterios con filtro de fechas"""
        from models import EstadoOperacion, Operacion
        
        query = self.db.query(Operacion)
        
        # Filtrar por fechas si se proporcionan
        if fecha_desde:
            query = query.filter(Operacion.fecha_creacion >= fecha_desde)
        if fecha_hasta:
            # Agregar un día para incluir toda la fecha_hasta
            from datetime import datetime, timedelta
            fecha_hasta_completa = datetime.combine(fecha_hasta, datetime.max.time())
            query = query.filter(Operacion.fecha_creacion <= fecha_hasta_completa)
        
        operaciones = query.filter(Operacion.estado == EstadoOperacion.ACTIVA).all()
        
        if not operaciones:
            return {
                "total_operaciones": 0,
                "margen_total": 0,
                "margen_promedio": 0,
                "margen_porcentaje_promedio": 0
            }
        
        margen_total = sum(op.margen_calculado or 0 for op in operaciones)
        margen_promedio = margen_total / len(operaciones)
        margen_porcentaje_promedio = sum(op.margen_porcentaje or 0 for op in operaciones) / len(operaciones)
        
        return {
            "total_operaciones": len(operaciones),
            "margen_total": margen_total,
            "margen_promedio": margen_promedio,
            "margen_porcentaje_promedio": margen_porcentaje_promedio
        }

class MovimientoFinancieroService:
    """Servicio para gestionar movimientos financieros"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    def actualizar_estado_pagos(self, operacion_id: int):
        """Actualiza el estado de los pagos programados basado en los movimientos realizados"""
        from models import PagoProgramado, EstadoPago, MovimientoFinanciero, TipoMovimiento, TipoPago
        
        # Obtener todos los pagos programados de la operación
        pagos = self.db.query(PagoProgramado).filter(
            PagoProgramado.operacion_id == operacion_id
        ).order_by(PagoProgramado.numero_pago).all()
        
        # Obtener movimientos de la operación
        movimientos = self.obtener_movimientos_por_operacion(operacion_id)
        
        # Separar movimientos por tipo
        depositos = [m for m in movimientos if m.tipo == TipoMovimiento.DEPOSITO_OPERACION]
        cobros = [m for m in movimientos if m.tipo == TipoMovimiento.COBRO_OPERACION]
        
        # Calcular totales una sola vez
        depositos_totales = sum(d.monto_salida for d in depositos)
        cobros_totales = sum(c.monto_entrada for c in cobros)
        
        # Actualizar estado de pagos de depósitos
        for pago in [p for p in pagos if p.tipo == TipoPago.PAGO]:
            # Calcular el monto del pago basado en el costo total
            costo_total = pago.operacion.valor_compra + pago.operacion.costo_flete + pago.operacion.costo_despachante
            monto_pago = costo_total * pago.porcentaje / 100
            if depositos_totales >= monto_pago:
                pago.estado = EstadoPago.PAGADO
                pago.fecha_real_pago = max(d.fecha for d in depositos) if depositos else None
            else:
                pago.estado = EstadoPago.PENDIENTE
                pago.fecha_real_pago = None
        
        # Actualizar estado de pagos de cobros
        for pago in [p for p in pagos if p.tipo == TipoPago.COBRO]:
            monto_pago = pago.operacion.precio_venta * pago.porcentaje / 100
            if cobros_totales >= monto_pago:
                pago.estado = EstadoPago.PAGADO
                pago.fecha_real_pago = max(c.fecha for c in cobros) if cobros else None
            else:
                pago.estado = EstadoPago.PENDIENTE
                pago.fecha_real_pago = None
        
        self.db.commit()

    def crear_movimiento(self, fecha: date, tipo, descripcion: str,
                        monto_entrada: float = 0.0, monto_salida: float = 0.0,
                        referencia: str = None, observaciones: str = None,
                        operacion_id: int = None,
                        impuestos_personalizados: list = None):
        """Crea un nuevo movimiento financiero validando el saldo disponible"""
        from models import MovimientoFinanciero, TipoMovimiento, Operacion
        try:
            # Verificar saldo disponible si es un egreso
            if monto_salida > 0:
                saldo_info = self.calcular_saldo()
                if monto_salida > saldo_info['saldo_actual']:
                    raise ValueError(f"Saldo insuficiente. Disponible: ${saldo_info['saldo_actual']:,.2f}")

            # Si es un depósito de operación, verificar el monto contra la operación
            if tipo == TipoMovimiento.DEPOSITO_OPERACION and operacion_id:
                operacion = self.db.query(Operacion).filter(Operacion.id == operacion_id).first()
                if not operacion:
                    raise ValueError("Operación no encontrada")
                
                # Calcular total de depósitos ya realizados para esta operación
                depositos_previos = sum(
                    mov.monto_salida for mov in self.obtener_movimientos_por_operacion(operacion_id)
                    if mov.tipo == TipoMovimiento.DEPOSITO_OPERACION
                )
                
                # Calcular el costo total de la operación incluyendo costos adicionales
                costo_total = operacion.valor_compra + operacion.costo_flete + operacion.costo_despachante
                
                if depositos_previos + monto_salida > costo_total:
                    raise ValueError(f"El total de depósitos (${depositos_previos + monto_salida:,.2f}) superaría el costo total (${costo_total:,.2f})")

            movimiento = MovimientoFinanciero(
                fecha=fecha,
                tipo=tipo,
                descripcion=descripcion,
                monto_entrada=monto_entrada,
                monto_salida=monto_salida,
                referencia=referencia,
                observaciones=observaciones,
                operacion_id=operacion_id
            )
            self.db.add(movimiento)
            
            # Actualizar estado de pagos si el movimiento está relacionado con una operación
            if operacion_id and tipo in [TipoMovimiento.DEPOSITO_OPERACION, TipoMovimiento.COBRO_OPERACION]:
                self.db.flush()  # Para obtener el ID del movimiento
                self.actualizar_estado_pagos(operacion_id)
            
            self.db.commit()
            self.db.refresh(movimiento)
            self.logger.info(f"Movimiento creado: {movimiento.id} - {descripcion}")
            return movimiento
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error al crear movimiento: {str(e)}")
            raise
    
    def obtener_movimientos(self, fecha_desde: date = None, fecha_hasta: date = None):
        """Obtiene movimientos financieros con filtro de fechas"""
        from models import MovimientoFinanciero
        
        try:
            query = self.db.query(MovimientoFinanciero)
            
            if fecha_desde:
                query = query.filter(MovimientoFinanciero.fecha >= fecha_desde)
            if fecha_hasta:
                query = query.filter(MovimientoFinanciero.fecha <= fecha_hasta)
            
            movimientos = query.order_by(MovimientoFinanciero.fecha.desc()).all()
            self.logger.info(f"Obtenidos {len(movimientos)} movimientos")
            return movimientos
            
        except Exception as e:
            self.logger.error(f"Error al obtener movimientos: {str(e)}")
            raise

    def obtener_movimientos_por_operacion(self, operacion_id: int):
        """Obtiene todos los movimientos relacionados con una operación"""
        from models import MovimientoFinanciero
        
        try:
            movimientos = self.db.query(MovimientoFinanciero).filter(
                MovimientoFinanciero.operacion_id == operacion_id
            ).order_by(MovimientoFinanciero.fecha.desc()).all()
            
            self.logger.info(f"Obtenidos {len(movimientos)} movimientos para la operación {operacion_id}")
            return movimientos
        except Exception as e:
            self.logger.error(f"Error al obtener movimientos de la operación {operacion_id}: {str(e)}")
            raise

    def calcular_saldo_operacion(self, operacion_id: int):
        """Calcula el saldo total de una operación específica"""
        try:
            movimientos = self.obtener_movimientos_por_operacion(operacion_id)
            saldo = sum(mov.monto for mov in movimientos)
            self.logger.info(f"Saldo calculado para operación {operacion_id}: {saldo}")
            return saldo
        except Exception as e:
            self.logger.error(f"Error al calcular saldo de la operación {operacion_id}: {str(e)}")
            raise
    
    def calcular_saldo(self, fecha_hasta: date = None) -> dict:
        """Calcula el saldo y proyección de cash flow hasta una fecha determinada - ACTUALIZADO"""
        from models import MovimientoFinanciero, TipoMovimiento, PagoProgramado, EstadoPago, Operacion, TipoPago
        from datetime import date as date_class, timedelta
        
        try:
            if fecha_hasta is None:
                fecha_hasta = date_class.today()
            
            # PASO 1: Obtener todos los movimientos financieros realizados hasta la fecha
            movimientos = self.db.query(MovimientoFinanciero).filter(
                MovimientoFinanciero.fecha <= fecha_hasta
            ).all()
            
            # PASO 2: Calcular saldo actual SOLO basado en movimientos reales
            total_entradas = 0
            total_salidas = 0
            depositos_operaciones = 0
            cobros_operaciones = 0
            
            for mov in movimientos:
                # Procesar entradas (ingresos de dinero)
                if mov.monto_entrada > 0:
                    total_entradas += mov.monto_entrada
                    if mov.tipo == TipoMovimiento.COBRO_OPERACION:
                        cobros_operaciones += mov.monto_entrada
            
                # Procesar salidas (egresos de dinero)
                if mov.monto_salida > 0:
                    total_salidas += mov.monto_salida
                    if mov.tipo == TipoMovimiento.DEPOSITO_OPERACION:
                        depositos_operaciones += mov.monto_salida
            
            # Saldo actual = entradas - salidas
            saldo_actual = total_entradas - total_salidas
            
            # PASO 3: Calcular pagos vencidos y futuros
            depositos_pendientes = 0  # Pagos vencidos
            cobros_pendientes = 0     # Cobros vencidos
            depositos_futuros = 0     # Pagos futuros
            cobros_futuros = 0        # Cobros futuros
            
            # Obtener todos los pagos programados pendientes
            pagos_programados = self.db.query(PagoProgramado).join(Operacion).filter(
                PagoProgramado.estado == EstadoPago.PENDIENTE
            ).all()
            
            for pago in pagos_programados:
                if pago.tipo == TipoPago.PAGO:
                    # Depósitos: basado en costo total de la operación
                    costo_total = pago.operacion.valor_compra + pago.operacion.costo_flete + pago.operacion.costo_despachante
                    monto = costo_total * pago.porcentaje / 100
                    
                    if pago.fecha_programada <= fecha_hasta:
                        # Es un pago vencido
                        depositos_pendientes += monto
                    else:
                        # Es un pago futuro
                        depositos_futuros += monto
                        
                elif pago.tipo == TipoPago.COBRO:
                    # Cobros: basado en precio de venta
                    monto = pago.operacion.precio_venta * pago.porcentaje / 100
                    
                    if pago.fecha_programada <= fecha_hasta:
                        # Es un cobro vencido
                        cobros_pendientes += monto
                    else:
                        # Es un cobro futuro
                        cobros_futuros += monto
            
            # PASO 4: Calcular proyección por fechas (próximos 90 días)
            dias_proyeccion = 90
            fechas_proyeccion = [fecha_hasta + timedelta(days=i) for i in range(0, dias_proyeccion+1, 7)]
            proyeccion_saldos = {}
            
            for fecha in fechas_proyeccion:
                fecha_str = fecha.strftime('%Y-%m-%d')
                
                # Calcular ingresos y egresos acumulados hasta esta fecha
                ingresos_acum = 0
                egresos_acum = 0
                
                pagos_hasta_fecha = self.db.query(PagoProgramado).join(Operacion).filter(
                    PagoProgramado.estado == EstadoPago.PENDIENTE,
                    PagoProgramado.fecha_programada <= fecha,
                    PagoProgramado.fecha_programada > fecha_hasta  # Solo futuros
                ).all()
                
                for pago in pagos_hasta_fecha:
                    if pago.tipo == TipoPago.PAGO:
                        costo_total = pago.operacion.valor_compra + pago.operacion.costo_flete + pago.operacion.costo_despachante
                        monto = costo_total * pago.porcentaje / 100
                        egresos_acum += monto
                    elif pago.tipo == TipoPago.COBRO:
                        monto = pago.operacion.precio_venta * pago.porcentaje / 100
                        ingresos_acum += monto
                
                proyeccion_saldos[fecha_str] = {
                    'saldo': saldo_actual + ingresos_acum - egresos_acum,
                    'ingresos': ingresos_acum,
                    'egresos': egresos_acum
                }
            
            # Saldo proyectado = saldo actual + todos los cobros pendientes - todos los depósitos pendientes
            saldo_proyectado = saldo_actual + (cobros_pendientes + cobros_futuros) - (depositos_pendientes + depositos_futuros)
            
            # Log para debugging
            self.logger.info(f"CÁLCULO DE SALDO ACTUALIZADO:")
            self.logger.info(f"- Movimientos procesados: {len(movimientos)}")
            self.logger.info(f"- Total entradas: ${total_entradas:,.2f}")
            self.logger.info(f"- Total salidas: ${total_salidas:,.2f}")
            self.logger.info(f"- Saldo actual: ${saldo_actual:,.2f}")
            self.logger.info(f"- Depósitos vencidos: ${depositos_pendientes:,.2f}")
            self.logger.info(f"- Cobros vencidos: ${cobros_pendientes:,.2f}")
            self.logger.info(f"- Depósitos futuros: ${depositos_futuros:,.2f}")
            self.logger.info(f"- Cobros futuros: ${cobros_futuros:,.2f}")
            self.logger.info(f"- Saldo proyectado: ${saldo_proyectado:,.2f}")
            
            return {
                "fecha_corte": fecha_hasta,
                "total_entradas": total_entradas,
                "total_salidas": total_salidas,
                "saldo_actual": saldo_actual,
                "depositos_operaciones": depositos_operaciones,
                "cobros_operaciones": cobros_operaciones,
                "depositos_pendientes": depositos_pendientes,
                "cobros_pendientes": cobros_pendientes,
                "depositos_futuros": depositos_futuros,
                "cobros_futuros": cobros_futuros,
                "saldo_proyectado": saldo_proyectado,
                "proyeccion_saldos": proyeccion_saldos,
                "cantidad_movimientos": len(movimientos)
            }
            
        except Exception as e:
            self.logger.error(f"Error al calcular saldo: {str(e)}")
            raise

    def eliminar_movimiento(self, movimiento_id: int) -> bool:
        """Elimina un movimiento financiero por ID"""
        from models import MovimientoFinanciero
        
        try:
            movimiento = self.db.query(MovimientoFinanciero).filter(
                MovimientoFinanciero.id == movimiento_id
            ).first()
            
            if movimiento:
                # Los impuestos personalizados se eliminan automáticamente por cascade
                self.db.delete(movimiento)
                self.db.commit()
                logging.info(f"Movimiento {movimiento_id} eliminado correctamente")
                return True
            else:
                logging.warning(f"Movimiento {movimiento_id} no encontrado")
                return False
                
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error al eliminar movimiento {movimiento_id}: {str(e)}")
            raise

class HSCodeService:
    """Servicio para gestionar códigos HS e impuestos asociados"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def crear_hs_code(self, codigo: str, descripcion: str, impuestos: list = None):
        """Crea un nuevo código HS con sus impuestos asociados"""
        from models import HSCode, ImpuestoHS
        
        try:
            hs_code = HSCode(
                codigo=codigo,
                descripcion=descripcion
            )
            
            self.db.add(hs_code)
            self.db.flush()
            
            # Agregar impuestos asociados
            if impuestos:
                for impuesto_data in impuestos:
                    impuesto = ImpuestoHS(
                        hs_code_id=hs_code.id,
                        nombre=impuesto_data['nombre'],
                        porcentaje=impuesto_data['porcentaje'],
                        tipo=impuesto_data.get('tipo', 'PORCENTUAL')
                    )
                    self.db.add(impuesto)
            
            self.db.commit()
            self.db.refresh(hs_code)
            logging.info(f"HS Code creado: {hs_code.codigo}")
            return hs_code
            
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error al crear HS Code: {str(e)}")
            raise
    
    def obtener_hs_codes(self):
        """Obtiene todos los códigos HS"""
        from models import HSCode
        
        return self.db.query(HSCode).order_by(HSCode.codigo).all()
    
    def obtener_impuestos_por_hs(self, hs_code_id: int):
        """Obtiene impuestos asociados a un código HS"""
        from models import ImpuestoHS
        
        return self.db.query(ImpuestoHS).filter(
            ImpuestoHS.hs_code_id == hs_code_id
        ).all()

class FacturaService:
    """Servicio para gestionar facturas"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generar_factura(self, operacion_id: int, fecha_factura: date = None):
        """Genera una factura para una operación - CORREGIDO"""
        from models import Factura, Operacion
        from datetime import date as date_class
        
        try:
            operacion = self.db.query(Operacion).filter(Operacion.id == operacion_id).first()
            if not operacion:
                raise ValueError("Operación no encontrada")
                
            # Usar fecha actual si no se proporciona
            if fecha_factura is None:
                fecha_factura = date_class.today()
                
            # Validar fecha HBL
            if hasattr(operacion, 'fecha_hbl') and operacion.fecha_hbl:
                if fecha_factura >= operacion.fecha_hbl:
                    raise ValueError(f"La fecha de factura debe ser anterior al HBL ({operacion.fecha_hbl})")
            
            # Verificar que no exista ya una factura para esta operación
            factura_existente = self.db.query(Factura).filter(
                Factura.operacion_id == operacion_id
            ).first()
            
            if factura_existente:
                raise ValueError(f"Ya existe una factura para esta operación: {factura_existente.numero}")
            
            # Generar número de factura
            ultimo_numero = self.db.query(Factura).count()
            numero_factura = f"INV-{ultimo_numero + 1:06d}"
            
            factura = Factura(
                numero=numero_factura,
                fecha=fecha_factura,
                operacion_id=operacion_id,
                subtotal_fob=operacion.valor_compra,
                total_incoterm=operacion.precio_venta,
                moneda="USD"
            )
            
            self.db.add(factura)
            self.db.commit()
            self.db.refresh(factura)
            logging.info(f"Factura generada: {factura.numero}")
            
            return factura
            
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error al generar factura: {str(e)}")
            raise
    
    def generar_factura_personalizada(self, operacion_id: int, numero: str, 
                                     fecha_factura: date, subtotal_fob: float, 
                                     total_incoterm: float, moneda: str = "USD",
                                     descripcion: str = "", observaciones: str = ""):
        """Genera una factura con datos personalizados"""
        from models import Factura, Operacion
        
        try:
            operacion = self.db.query(Operacion).filter(Operacion.id == operacion_id).first()
            if not operacion:
                raise ValueError("Operación no encontrada")
                
            # Validar fecha HBL
            if hasattr(operacion, 'fecha_hbl') and operacion.fecha_hbl:
                if fecha_factura >= operacion.fecha_hbl:
                    raise ValueError(f"La fecha de factura debe ser anterior al HBL ({operacion.fecha_hbl})")
            
            # Verificar que no exista ya una factura para esta operación
            factura_existente = self.db.query(Factura).filter(
                Factura.operacion_id == operacion_id
            ).first()
            
            if factura_existente:
                raise ValueError(f"Ya existe una factura para esta operación: {factura_existente.numero}")
            
            # Verificar que el número de factura no exista
            numero_existente = self.db.query(Factura).filter(
                Factura.numero == numero
            ).first()
            
            if numero_existente:
                raise ValueError(f"Ya existe una factura con el número: {numero}")
            
            factura = Factura(
                numero=numero,
                fecha=fecha_factura,
                operacion_id=operacion_id,
                subtotal_fob=subtotal_fob,
                total_incoterm=total_incoterm,
                moneda=moneda,
                descripcion=descripcion,
                observaciones=observaciones
            )
            
            self.db.add(factura)
            self.db.commit()
            self.db.refresh(factura)
            logging.info(f"Factura personalizada generada: {factura.numero}")
            
            return factura
            
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error al generar factura personalizada: {str(e)}")
            raise

    def obtener_facturas(self):
        """Obtiene todas las facturas"""
        from models import Factura
        
        return self.db.query(Factura).order_by(Factura.fecha.desc()).all()
    
    def obtener_factura_por_operacion(self, operacion_id: int):
        """Obtiene la factura de una operación específica"""
        from models import Factura
        
        return self.db.query(Factura).filter(
            Factura.operacion_id == operacion_id
        ).first()

def migrate_database_fields():
    """Migra campos nuevos en la base de datos"""
    from sqlalchemy import create_engine, text
    
    DATABASE_URL = "sqlite:///comercio.db"
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Verificar si las columnas ya existen en contactos
            result = conn.execute(text("PRAGMA table_info(contactos)"))
            columns = [row[1] for row in result.fetchall()]
            
            # Agregar campos nuevos a contactos si no existen
            new_fields = {
                "provincia": "VARCHAR(100)",
                "numero_identificacion_fiscal": "VARCHAR(50)",
                "industria": "VARCHAR(50)",
                "direccion_fabrica": "VARCHAR(500)",
                "puerto_conveniente": "VARCHAR(200)"
            }
            
            for field, field_type in new_fields.items():
                if field not in columns:
                    conn.execute(text(f"ALTER TABLE contactos ADD COLUMN {field} {field_type}"))
                    logging.info(f"Agregada columna {field} a contactos")
            
            # Verificar si las columnas ya existen en facturas
            result = conn.execute(text("PRAGMA table_info(facturas)"))
            columns = [row[1] for row in result.fetchall()]
            
            # Agregar campos nuevos a facturas si no existen
            factura_fields = {
                "descripcion": "VARCHAR(1000)",
                "observaciones": "VARCHAR(1000)"
            }
            
            for field, field_type in factura_fields.items():
                if field not in columns:
                    conn.execute(text(f"ALTER TABLE facturas ADD COLUMN {field} {field_type}"))
                    logging.info(f"Agregada columna {field} a facturas")
            
            conn.commit()
            logging.info("Migración de campos completada exitosamente")
            
        except Exception as e:
            logging.error(f"Error en migración: {str(e)}")
            conn.rollback()

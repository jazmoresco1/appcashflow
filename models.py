# models.py - Modelos de base de datos
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
import logging

Base = declarative_base()

class TipoContacto(enum.Enum):
    PROVEEDOR = "proveedor"
    CLIENTE = "cliente"
    AGENTE_LOGISTICO = "agente_logistico"

class Industria(enum.Enum):
    AGRICOLA = "agricola"
    CONSTRUCCION = "construccion"
    TEXTIL = "textil"
    ALIMENTARIA = "alimentaria"
    AUTOMOTRIZ = "automotriz"
    TECNOLOGIA = "tecnologia"
    ENERGIA = "energia"
    FARMACEUTICA = "farmaceutica"
    QUIMICA = "quimica"
    METALURGICA = "metalurgica"
    MINERIA = "mineria"
    MADERERA = "maderera"
    PLASTICA = "plastica"
    OTRA = "otra"

class IncotermCompra(enum.Enum):
    FOB = "FOB"
    FCA = "FCA"
    EXW = "EXW"

class IncotermVenta(enum.Enum):
    DAP = "DAP"
    CIF = "CIF"
    FOB = "FOB"

class EstadoOperacion(enum.Enum):
    ACTIVA = "activa"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"

class TipoMovimiento(enum.Enum):
    APORTE_INICIAL = "aporte_inicial"
    ADELANTO = "adelanto"
    RETIRO = "retiro"
    DEPOSITO_OPERACION = "deposito_operacion"
    COBRO_OPERACION = "cobro_operacion"
    PAGO_IMPUESTOS = "pago_impuestos"  # Agregamos este valor

class Contacto(Base):
    __tablename__ = 'contactos'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    tipo = Column(Enum(TipoContacto), nullable=False)
    pais = Column(String(100))
    provincia = Column(String(100))  # Nuevo campo para provincia
    email = Column(String(200))
    telefono = Column(String(50))
    razon_social = Column(String(200))
    direccion_fiscal = Column(String(500))
    numero_identificacion_fiscal = Column(String(50))  # Reemplaza CUIT y EIN
    industria = Column(Enum(Industria))  # Nuevo campo para industria del cliente
    direccion_fabrica = Column(String(500))  # Nuevo campo para proveedores
    puerto_conveniente = Column(String(200))  # Nuevo campo para proveedores
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    operaciones_proveedor = relationship("Operacion", foreign_keys="Operacion.proveedor_id", back_populates="proveedor")
    operaciones_cliente = relationship("Operacion", foreign_keys="Operacion.cliente_id", back_populates="cliente")
    operaciones_agente = relationship("Operacion", foreign_keys="Operacion.agente_logistico_id", back_populates="agente_logistico")

class Operacion(Base):
    __tablename__ = 'operaciones'
    
    id = Column(Integer, primary_key=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Referencias a contactos
    proveedor_id = Column(Integer, ForeignKey('contactos.id'), nullable=False)
    cliente_id = Column(Integer, ForeignKey('contactos.id'), nullable=False)
    agente_logistico_id = Column(Integer, ForeignKey('contactos.id'))
    hs_code_id = Column(Integer, ForeignKey('hs_codes.id'))
    
    # Datos de compra
    incoterm_compra = Column(Enum(IncotermCompra), nullable=False)
    valor_compra = Column(Float, nullable=False)
    porcentaje_deposito = Column(Float, default=30.0)  # Default 30%
    fecha_deposito = Column(Date)
    fecha_estimada_pago_saldo = Column(Date)
    fecha_real_pago_saldo = Column(Date)
    
    # Costos adicionales
    costo_flete = Column(Float, default=0.0)
    costo_despachante = Column(Float, default=0.0)
    
    # Datos de venta
    incoterm_venta = Column(Enum(IncotermVenta), nullable=False)
    precio_venta = Column(Float, nullable=False)
    origen_bienes = Column(String(100))
    descripcion_venta = Column(String(500))
    observaciones = Column(String(1000))
    fecha_hbl = Column(Date)
    
    # Calculados automÃ¡ticamente
    margen_calculado = Column(Float)
    margen_porcentaje = Column(Float)
    
    # Control
    estado = Column(Enum(EstadoOperacion), default=EstadoOperacion.ACTIVA)
    
    # Relaciones
    proveedor = relationship("Contacto", foreign_keys=[proveedor_id], back_populates="operaciones_proveedor")
    cliente = relationship("Contacto", foreign_keys=[cliente_id], back_populates="operaciones_cliente")
    agente_logistico = relationship("Contacto", foreign_keys=[agente_logistico_id], back_populates="operaciones_agente")
    movimientos_financieros = relationship("MovimientoFinanciero", back_populates="operacion")
    pagos_programados = relationship("PagoProgramado", back_populates="operacion")
    hs_code = relationship("HSCode", back_populates="operaciones")
    factura = relationship("Factura", back_populates="operacion")
    
    def calcular_margen(self):
        """Calcula automÃ¡ticamente el margen de la operaciÃ³n"""
        costo_total = self.valor_compra + self.costo_flete + self.costo_despachante
        self.margen_calculado = self.precio_venta - costo_total
        self.margen_porcentaje = (self.margen_calculado / self.precio_venta) * 100 if self.precio_venta > 0 else 0
        return self.margen_calculado

class EstadoPago(enum.Enum):
    PENDIENTE = "pendiente"
    PAGADO = "pagado"
    CANCELADO = "cancelado"

class TipoPago(enum.Enum):
    PAGO = "pago"
    COBRO = "cobro"

class PagoProgramado(Base):
    __tablename__ = 'pagos_programados'
    
    id = Column(Integer, primary_key=True)
    operacion_id = Column(Integer, ForeignKey('operaciones.id'), nullable=False)
    numero_pago = Column(Integer, nullable=False)
    descripcion = Column(String(500))
    porcentaje = Column(Float, nullable=False)
    fecha_programada = Column(Date, nullable=False)
    fecha_real_pago = Column(Date)
    estado = Column(Enum(EstadoPago), default=EstadoPago.PENDIENTE)
    tipo = Column(Enum(TipoPago), default=TipoPago.PAGO)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Relación
    operacion = relationship("Operacion", back_populates="pagos_programados")

class HSCode(Base):
    __tablename__ = 'hs_codes'
    
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), nullable=False, unique=True)
    descripcion = Column(String(500), nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    operaciones = relationship("Operacion", back_populates="hs_code")
    impuestos = relationship("ImpuestoHS", back_populates="hs_code")

class ImpuestoHS(Base):
    __tablename__ = 'impuestos_hs'
    
    id = Column(Integer, primary_key=True)
    hs_code_id = Column(Integer, ForeignKey('hs_codes.id'), nullable=False)
    nombre = Column(String(200), nullable=False)
    porcentaje = Column(Float, nullable=False)
    tipo = Column(String(50), default="PORCENTUAL")
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Relación
    hs_code = relationship("HSCode", back_populates="impuestos")

class MovimientoFinanciero(Base):
    __tablename__ = 'movimientos_financieros'
    id = Column(Integer, primary_key=True)
    fecha = Column(Date, nullable=False)
    tipo = Column(Enum(TipoMovimiento), nullable=False)
    descripcion = Column(String(500), nullable=False)
    monto_entrada = Column(Float, default=0.0)
    monto_salida = Column(Float, default=0.0)
    referencia = Column(String(200))
    observaciones = Column(String(1000))
    operacion_id = Column(Integer, ForeignKey('operaciones.id'))
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    # Relación
    operacion = relationship("Operacion", back_populates="movimientos_financieros")

class Factura(Base):
    __tablename__ = 'facturas'
    
    id = Column(Integer, primary_key=True)
    numero = Column(String(50), nullable=False, unique=True)
    fecha = Column(Date, nullable=False)
    operacion_id = Column(Integer, ForeignKey('operaciones.id'), nullable=False)
    subtotal_fob = Column(Float, nullable=False)
    total_incoterm = Column(Float, nullable=False)
    moneda = Column(String(10), default="USD")
    descripcion = Column(String(1000))  # Descripción de productos/servicios
    observaciones = Column(String(1000))  # Observaciones adicionales
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Relación
    operacion = relationship("Operacion", back_populates="factura")

# Configuración de la base de datos
DATABASE_URL = "sqlite:///comercio.db"  # Base de datos principal

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_database():
    """Inicializa la base de datos creando todas las tablas si no existen"""
    try:
        # Intentar crear las tablas solo si no existen
        Base.metadata.create_all(bind=engine)
        logging.info("Base de datos inicializada correctamente")
    except Exception as e:
        logging.error(f"Error al inicializar la base de datos: {str(e)}")
        raise

def get_db():
    """Obtiene una sesiÃ³n de base de datos"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

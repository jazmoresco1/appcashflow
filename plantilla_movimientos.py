# plantilla_movimientos.py - Genera plantilla Excel para cargar movimientos
import pandas as pd
from datetime import date, timedelta

def generar_plantilla_excel():
    """Genera un DataFrame con el formato correcto para cargar movimientos"""
    
    # Datos de ejemplo para la plantilla
    ejemplo_data = {
        "Factura": [
            "FAC-2025-001", 
            "FAC-2025-002", 
            "FAC-2025-003"
        ],
        "Fecha": [
            "2025-01-15", 
            "2025-01-20", 
            "2025-01-25"
        ],
        "Proveedor": [
            "Proveedor Ejemplo ABC", 
            "Supplier XYZ Ltd", 
            "Manufacturer 123"
        ],
        "Codigo_Producto": [
            "PROD001", 
            "ELEC002", 
            "AUTO003"
        ],
        "Cliente": [
            "Cliente Premium SA", 
            "Empresa Importadora", 
            "Distribuidora Nacional"
        ],
        "INCOTERM": [
            "FOB", 
            "CIF", 
            "DAP"
        ],
        "Origen": [
            "China", 
            "Brasil", 
            "Alemania"
        ],
        "Puerto_Origen": [
            "Puerto de Shanghai", 
            "Puerto de Santos", 
            "Puerto de Hamburgo"
        ],
        "Destino_Final": [
            "Buenos Aires, Argentina", 
            "Montevideo, Uruguay", 
            "Santiago, Chile"
        ],
        "Valor_Compra_FOB": [
            5000.00, 
            12500.75, 
            8750.50
        ],
        "Porcentaje_Deposito": [
            30, 
            50, 
            40
        ],
        "Fecha_Deposito": [
            "2025-01-10", 
            "2025-01-15", 
            "2025-01-20"
        ],
        "Fecha_Pago_Saldo": [
            "2025-03-15", 
            "2025-03-20", 
            "2025-03-25"
        ],
        "Valor_Venta": [
            6000.00, 
            15000.00, 
            10500.00
        ],
        "Numero_Cuotas": [
            1, 
            2, 
            3
        ],
        "Fechas_Cuotas": [
            "2025-03-15", 
            "2025-03-20;2025-04-20", 
            "2025-03-25;2025-04-25;2025-05-25"
        ],
        "Observaciones": [
            "Entrega urgente - Cliente premium", 
            "Incluye seguro adicional", 
            "Pago contra documentos"
        ]
    }
    
    return pd.DataFrame(ejemplo_data)

def generar_plantilla_vacia():
    """Genera una plantilla vacía solo con las columnas"""
    
    columnas = [
        "Factura",
        "Fecha", 
        "Proveedor",
        "Codigo_Producto",
        "Cliente",
        "INCOTERM",
        "Origen",
        "Puerto_Origen", 
        "Destino_Final",
        "Valor_Compra_FOB",
        "Porcentaje_Deposito",
        "Fecha_Deposito",
        "Fecha_Pago_Saldo",
        "Valor_Venta",
        "Numero_Cuotas",
        "Fechas_Cuotas",
        "Observaciones"
    ]
    
    # Crear DataFrame vacío con una fila de ejemplo
    data = {col: [""] for col in columnas}
    
    # Agregar una fila de ejemplo con placeholder
    data["Factura"] = ["FAC-YYYY-XXX"]
    data["Fecha"] = ["YYYY-MM-DD"]
    data["Proveedor"] = ["Nombre del proveedor (debe existir en sistema)"]
    data["Codigo_Producto"] = ["Código único del producto"]
    data["Cliente"] = ["Nombre del cliente (debe existir en sistema)"]
    data["INCOTERM"] = ["FOB, CIF, DAP, etc."]
    data["Origen"] = ["País o ciudad de origen"]
    data["Puerto_Origen"] = ["Puerto de embarque"]
    data["Destino_Final"] = ["Ciudad/país de destino final"]
    data["Valor_Compra_FOB"] = ["Valor numérico sin comas"]
    data["Porcentaje_Deposito"] = ["30, 50, etc. (solo número)"]
    data["Fecha_Deposito"] = ["YYYY-MM-DD"]
    data["Fecha_Pago_Saldo"] = ["YYYY-MM-DD"]
    data["Valor_Venta"] = ["Valor numérico sin comas"]
    data["Numero_Cuotas"] = ["1, 2, 3, etc."]
    data["Fechas_Cuotas"] = ["YYYY-MM-DD;YYYY-MM-DD (separar con ;)"]
    data["Observaciones"] = ["Información adicional opcional"]
    
    return pd.DataFrame(data)

def obtener_instrucciones():
    """Devuelve las instrucciones para completar la plantilla"""
    
    instrucciones = """
INSTRUCCIONES PARA COMPLETAR LA PLANTILLA:

CAMPOS OBLIGATORIOS:
- Factura: Número único de factura (ej: FAC-2025-001)
- Fecha: Fecha de la operación en formato YYYY-MM-DD
- Proveedor: Nombre exacto del proveedor (debe existir en el sistema)
- Cliente: Nombre exacto del cliente (debe existir en el sistema)
- Valor_Compra_FOB: Valor de compra en USD (usar punto decimal)
- Valor_Venta: Valor de venta en USD (usar punto decimal)

CAMPOS OPCIONALES:
- Codigo_Producto: Identificador del producto
- INCOTERM: Términos de comercio (FOB, CIF, DAP, etc.)
- Origen: País o ciudad de origen
- Puerto_Origen: Puerto de embarque
- Destino_Final: Destino final de la mercancía
- Porcentaje_Deposito: % del depósito inicial (default: 30)
- Fecha_Deposito: Fecha del depósito inicial
- Fecha_Pago_Saldo: Fecha estimada del pago del saldo
- Numero_Cuotas: Cantidad de cuotas de cobro (default: 1)
- Fechas_Cuotas: Fechas de cobro separadas por ; (punto y coma)
- Observaciones: Información adicional

FORMATOS IMPORTANTES:
- Fechas: YYYY-MM-DD (ej: 2025-01-15)
- Valores: Usar punto para decimales (ej: 1500.50)
- Múltiples fechas: Separar con ; (ej: 2025-01-15;2025-02-15)
- No usar comas en números

VALIDACIONES:
- Los proveedores y clientes deben existir en el sistema
- El valor de venta debe ser mayor al valor de compra
- Las fechas deben ser válidas
- Los valores numéricos deben ser positivos

¡IMPORTANTE!
Borra esta fila de instrucciones antes de subir el archivo.
"""
    
    return instrucciones

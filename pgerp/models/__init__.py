"""PyGo ERP — Core Business Models.

ERP modules covering:
- Company/Multi-tenancy (Empresa)
- Products (Producto, Categoria)
- Contacts (Cliente, Proveedor)
- Accounting (Factura, Cuenta, Asiento)
- Inventory (Inventario, Movimiento)
- Sales (Pedido, PedidoLinea)
- Purchasing (OrdenCompra, OrdenLinea)
- Human Resources (Empleado, Departamento, Puesto)
- Project Management (Proyecto, Tarea, Timesheet)
"""

from core import Model, UUID, Email, Decimal, DateTime, String, Boolean, Array, Enum
from datetime import datetime, date
from decimal import Decimal as D
from typing import Optional, List
from dataclasses import dataclass, field


# ─── Multi-Tenancy ───
@dataclass
class Empresa(Model):
    """Company (tenant root)."""
    rfc: str = field(metadata={"max": 20})
    razon_social: str = field(metadata={"max": 200})
    nombre_comercial: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    estado: Optional[str] = None
    codigo_postal: Optional[str] = None
    pais: str = "MX"
    moneda: str = "MXN"
    activo: bool = True

    _table = "empresas"
    _timestamps = True


@dataclass
class Usuario(Model):
    """System user."""
    nombre: str = field(metadata={"max": 200})
    email: str = field(metadata={"type": "email"})
    password_hash: str = field(metadata={"max": 256})
    rol: str = "usuario"
    empresa: str = None  # FK to Empresa

    _table = "usuarios"
    _timestamps = True
    _hidden = ["password_hash"]
    _enum = {"rol": ["admin", "gerente", "usuario", "cliente"]}


@dataclass
class Permiso(Model):
    """RBAC permission."""
    codigo: str = field(metadata={"max": 100})
    descripcion: Optional[str] = None
    roles: List[str] = field(default_factory=list)

    _table = "permisos"
    _timestamps = True


# ─── Catalogs ───
@dataclass
class Categoria(Model):
    """Product/service category."""
    nombre: str = field(metadata={"max": 100})
    descripcion: Optional[str] = None
    tipo: str = "producto"  # producto | servicio | inventario
    empresa: Optional[str] = None

    _table = "categorias"
    _enum = {"tipo": ["producto", "servicio", "inventario"]}


@dataclass
class UnidadMedida(Model):
    """Unit of measure."""
    clave: str = field(metadata={"max": 20})
    descripcion: str = field(metadata={"max": 200})
    tipo: str = "longitud"  # longitud | peso | volumen | unidad

    _table = "unidades_medida"
    _enum = {"tipo": ["longitud", "peso", "volumen", "unidad"]}


@dataclass
class Impuesto(Model):
    """Tax definition (IVA, IEPS, etc)."""
    codigo: str = field(metadata={"max": 20})
    descripcion: str = field(metadata={"max": 200})
    tipo: str = "iva"  # iva | ieps | local
    tasa: Decimal = D("0.00")
    activo: bool = True

    _table = "impuestos"
    _enum = {"tipo": ["iva", "ieps", "local"]}


@dataclass
class Moneda(Model):
    """Currency definition."""
    codigo: str = field(metadata={"max": 3})  # MXN, USD, EUR
    nombre: str = field(metadata={"max": 100})
    simbolo: str = field(metadata={"max": 10})
    tipo_cambio: Decimal = D("1.00")
    fecha_tipo_cambio: date = field(default_factory=date.today)

    _table = "monedas"


# ─── Products ───
@dataclass
class Producto(Model):
    """Product or service."""
    codigo: str = field(metadata={"max": 50})
    nombre: str = field(metadata={"max": 200})
    descripcion: Optional[str] = None
    tipo: str = "producto"  # producto | servicio
    categoria: Optional[str] = None
    unidad_medida: str = "pz"
    precio_unitario: Decimal = D("0.00")
    costo: Optional[Decimal] = None
    precio_mayoreo: Optional[Decimal] = None
    imagen: Optional[str] = None
    stock_minimo: Decimal = D("0")
    empresa: str = None

    _table = "productos"
    _timestamps = True
    _enum = {"tipo": ["producto", "servicio"]}


@dataclass
class ProductoImpuesto(Model):
    """Many-to-many: Producto <-> Impuesto."""
    producto: str = None
    impuesto: str = None

    _table = "productos_impuestos"


# ─── Contacts ───
@dataclass
class Cliente(Model):
    """Customer client."""
    nombre: str = field(metadata={"max": 200})
    rfc: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    estado: Optional[str] = None
    pais: str = "MX"
    empresa: str = None

    _table = "clientes"
    _timestamps = True


@dataclass
class Proveedor(Model):
    """Supplier vendor."""
    nombre: str = field(metadata={"max": 200})
    rfc: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    estado: Optional[str] = None
    pais: str = "MX"
    empresa: str = None

    _table = "proveedores"
    _timestamps = True


# ─── Accounting ───
@dataclass
class Cuenta(Model):
    """Chart of accounts."""
    codigo: str = field(metadata={"max": 20})
    nombre: str = field(metadata={"max": 200})
    tipo: str = "activo"  # activo | pasivo | capital | ingreso | gasto
    naturaleza: str = "debe"  # debe | haber
    empresa: str = None

    _table = "cuentas"
    _enum = {"tipo": ["activo", "pasivo", "capital", "ingreso", "gasto"], "naturaleza": ["debe", "haber"]}


@dataclass
class Factura(Model):
    """Invoice (sales or purchase)."""
    tipo: str = "venta"  # venta | compra
    folio: str = field(metadata={"max": 50})
    serie: Optional[str] = None
    fecha: datetime = field(default_factory=datetime.now)
    subtotal: Decimal = D("0.00")
    iva: Decimal = D("0.00")
    total: Decimal = D("0.00")
    cliente: Optional[str] = None
    proveedor: Optional[str] = None
    estatus: str = "borrador"  # borrador | timbrada | pagada | cancelada
    empresa: str = None

    _table = "facturas"
    _timestamps = True
    _enum = {"tipo": ["venta", "compra"], "estatus": ["borrador", "timbrada", "pagada", "cancelada"]}


@dataclass
class FacturaLinea(Model):
    """Invoice line item."""
    factura: str = None
    producto: Optional[str] = None
    cantidad: Decimal = D("1")
    precio_unitario: Decimal = D("0.00")
    descuento: Decimal = D("0.00")
    total_linea: Decimal = D("0.00")

    _table = "facturas_lineas"


@dataclass
class Pago(Model):
    """Payment."""
    tipo: str = "efectivo"  # efectivo | tarjeta | transferencia
    monto: Decimal = D("0.00")
    fecha: datetime = field(default_factory=datetime.now)
    factura: Optional[str] = None
    empresa: str = None

    _table = "pagos"
    _timestamps = True
    _enum = {"tipo": ["efectivo", "tarjeta", "transferencia"]}


# ─── Inventory ───
@dataclass
class Almacen(Model):
    """Warehouse."""
    nombre: str = field(metadata={"max": 100})
    direccion: Optional[str] = None
    empresa: str = None

    _table = "almacenes"


@dataclass
class Inventario(Model):
    """Inventory tracking."""
    producto: str = None
    almacen: str = "default"
    stock_actual: Decimal = D("0")
    stock_minimo: Decimal = D("0")
    ubicacion: Optional[str] = None
    empresa: str = None

    _table = "inventarios"


@dataclass
class MovimientoInventario(Model):
    """Inventory transaction."""
    tipo: str = "entrada"  # entrada | salida
    producto: str = None
    almacen: str = None
    cantidad: Decimal = D("1")
    fecha: datetime = field(default_factory=datetime.now)
    documento: Optional[str] = None  # factura/pedido ref
    empresa: str = None

    _table = "movimientos_inventario"
    _enum = {"tipo": ["entrada", "salida"]}


# ─── Sales ───
@dataclass
class Pedido(Model):
    """Sales order."""
    tipo: str = "pedido"  # pedido | cotizacion
    folio: str = None
    fecha: datetime = field(default_factory=datetime.now)
    cliente: str = None
    subtotal: Decimal = D("0.00")
    iva: Decimal = D("0.00")
    total: Decimal = D("0.00")
    estatus: str = "borrador"  # borrador | confirmado | entregado | cancelado
    empresa: str = None

    _table = "pedidos"
    _enum = {"tipo": ["pedido", "cotizacion"], "estatus": ["borrador", "confirmado", "entregado", "cancelado"]}


@dataclass
class PedidoLinea(Model):
    """Sales order line."""
    pedido: str = None
    producto: str = None
    cantidad: Decimal = D("1")
    precio_unitario: Decimal = D("0.00")
    total_linea: Decimal = D("0.00")

    _table = "pedidos_lineas"


# ─── Purchasing ───
@dataclass
class OrdenCompra(Model):
    """Purchase order."""
    folio: str = None
    fecha: datetime = field(default_factory=datetime.now)
    proveedor: str = None
    subtotal: Decimal = D("0.00")
    iva: Decimal = D("0.00")
    total: Decimal = D("0.00")
    estatus: str = "borrador"  # borrador | confirmado | recibido | cancelado
    empresa: str = None

    _table = "ordenes_compra"
    _enum = {"estatus": ["borrador", "confirmado", "recibido", "cancelado"]}


@dataclass
class OrdenCompraLinea(Model):
    """Purchase order line."""
    orden: str = None
    producto: str = None
    cantidad: Decimal = D("1")
    precio_unitario: Decimal = D("0.00")
    total_linea: Decimal = D("0.00")

    _table = "ordenes_compra_lineas"


# ─── HR ───
@dataclass
class Departamento(Model):
    """HR department."""
    nombre: str = field(metadata={"max": 100})
    gerente: Optional[str] = None
    empresa: str = None

    _table = "departamentos"


@dataclass
class Puesto(Model):
    """Job position."""
    nombre: str = field(metadata={"max": 100})
    descripcion: Optional[str] = None
    salario_min: Optional[Decimal] = None
    salario_max: Optional[Decimal] = None
    empresa: str = None

    _table = "puestos"


@dataclass
class Empleado(Model):
    """Employee."""
    usuario: str = None  # FK to Usuario
    nombre: str = field(metadata={"max": 200})
    apellidos: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    fecha_ingreso: date = field(default_factory=date.today)
    departamento: Optional[str] = None
    puesto: Optional[str] = None
    salario: Optional[Decimal] = None
    empresa: str = None

    _table = "empleados"
    _timestamps = True


# ─── Projects ───
@dataclass
class Proyecto(Model):
    """Project."""
    nombre: str = field(metadata={"max": 200})
    descripcion: Optional[str] = None
    cliente: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    estatus: str = "activo"  # activo | en_progreso | completado | cancelado
    presupuesto: Optional[Decimal] = None
    empresa: str = None

    _table = "proyectos"
    _enum = {"estatus": ["activo", "en_progreso", "completado", "cancelado"]}


@dataclass
class Tarea(Model):
    """Project task."""
    proyecto: str = None
    titulo: str = field(metadata={"max": 200})
    descripcion: Optional[str] = None
    responsable: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    estatus: str = "pendiente"  # pendiente | en_progreso | completado
    prioridad: str = "normal"  # baja | normal | alta | critica

    _table = "tareas"
    _enum = {"estatus": ["pendiente", "en_progreso", "completado"], "prioridad": ["baja", "normal", "alta", "critica"]}


@dataclass
class Timesheet(Model):
    """Time tracking."""
    tarea: str = None
    empleado: str = None
    fecha: date = field(default_factory=date.today)
    horas: Decimal = D("0.00")
    descripcion: Optional[str] = None

    _table = "timesheets"

"""PyGo ERP — Enterprise Resource Planning models.

Core ERP database models showcasing PyGo Framework capabilities:
- Multi-tenancy aware models
- CRUD operations
- HTMX-compatible serialization
- Relations (ForeignKey, OneToMany, ManyToMany)
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from dataclasses import dataclass, field

from core import Model, UUID, Email, Decimal as PyGoDecimal, DateTime, String, Boolean


@dataclass
class Empresa(Model):
    """Company/organization model (tenant root)."""
    rfc: str = field(metadata={"max": 20})
    razon_social: str = field(metadata={"max": 200})
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    activo: bool = True

    _table = "empresas"
    _timestamps = True


@dataclass
class Categoria(Model):
    """Product/service category."""
    nombre: str = field(metadata={"max": 100})
    descripcion: Optional[str] = None
    empresa: Optional[str] = None  # FK to Empresa

    _table = "categorias"


@dataclass
class Producto(Model):
    """Product or service."""
    codigo: str = field(metadata={"max": 50})
    nombre: str = field(metadata={"max": 200})
    descripcion: Optional[str] = None
    precio_unitario: Decimal = field(default=Decimal("0.00"))
    costo: Optional[Decimal] = None
    unidad_medida: str = "pz"
    categoria: Optional[str] = None  # FK to Categoria
    empresa: str = None  # FK to Empresa (required)
    activo: bool = True

    _table = "productos"
    _timestamps = True


@dataclass
class Cliente(Model):
    """Customer client."""
    nombre: str = field(metadata={"max": 200})
    rfc: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    empresa: str = None  # FK to Empresa (required)

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
    empresa: str = None  # FK to Empresa (required)

    _table = "proveedores"
    _timestamps = True


@dataclass
class Factura(Model):
    """Invoice header (sales or purchase)."""
    tipo: str = "venta"  # venta | compra
    folio: str = field(metadata={"max": 50})
    fecha: datetime = field(default_factory=datetime.now)
    total: Decimal = field(default=Decimal("0.00"))
    subtotal: Decimal = field(default=Decimal("0.00"))
    iva: Decimal = field(default=Decimal("0.00"))
    cliente: Optional[str] = None  # FK to Cliente
    proveedor: Optional[str] = None  # FK to Proveedor
    empresa: str = None  # FK to Empresa (required)
    estatus: str = "borrador"  # borrador | timbrada | cancelada

    _table = "facturas"
    _timestamps = True


@dataclass
class FacturaLinea(Model):
    """Invoice line item."""
    factura: str = None  # FK to Factura (required)
    producto: Optional[str] = None  # FK to Producto
    cantidad: Decimal = Decimal("1")
    precio_unitario: Decimal = Decimal("0.00")
    total_linea: Decimal = Decimal("0.00")

    _table = "facturas_lineas"


@dataclass
class Inventario(Model):
    """Inventory tracking per product/warehouse."""
    producto: str = None  # FK to Producto (required)
    almacen: str = "default"
    stock_actual: Decimal = Decimal("0")
    stock_minimo: Decimal = Decimal("0")
    empresa: str = None  # FK to Empresa (required)

    _table = "inventarios"

    def save(self) -> "Inventario":
        """Override save to auto-calculate stock."""
        self.stock_actual = max(Decimal("0"), self.stock_actual)
        return super().save()


@dataclass
class Usuario(Model):
    """System user (employee)."""
    nombre: str = field(metadata={"max": 200})
    email: str = field(metadata={"type": "email"})
    password_hash: str = field(metadata={"max": 256})
    rol: str = "usuario"  # admin | usuario | cliente
    empresa: str = None  # FK to Empresa (required)

    _table = "usuarios"
    _timestamps = True
    _hidden = ["password_hash"]


@dataclass
class Configuracion(Model):
    """Global configuration key-value store."""
    llave: str = field(metadata={"max": 100})
    valor: str = field(metadata={"max": 1000})
    empresa: Optional[str] = None  # FK to Empresa

    _table = "configuraciones"

    @classmethod
    def get(cls, key: str, default: str = None, empresa: str = None) -> Optional[str]:
        """Get configuration value by key."""
        query = cls.where("llave", key)
        if empresa:
            query = query.where("empresa", empresa)
        record = query.first()
        return record.valor if record else default

    @classmethod
    def set(cls, key: str, valor: str, empresa: str = None) -> None:
        """Set configuration value (creates or updates)."""
        record = cls.where("llave", key)
        if empresa:
            record = record.where("empresa", empresa)
        record = record.first()

        if record:
            record.valor = valor
            record.save()
        else:
            cls(llave=key, valor=valor, empresa=empresa).save()

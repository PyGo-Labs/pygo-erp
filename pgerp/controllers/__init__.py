# Import all ERP models
from models import (
  Empresa, Usuario, Producto, Categoria, Cliente, Proveedor,
  Factura, FacturaLinea, Pago,
  Inventario, Almacen, MovimientoInventario,
  Pedido, PedidoLinea, OrdenCompra, OrdenCompraLinea,
  Departamento, Puesto, Empleado, Proyecto, Tarea, Timesheet,
  UnidadMedida, Impuesto, Moneda, Cuenta, ProductoImpuesto, Permiso,
)
from core import Model, QueryBuilder, Array, Enum, Optional
from auth import current_user, auth_required, RBAC
from admin import AdminController, TableView, FormView, DetailView

# ═══════════════════════════════════════════════
#  ADMIN CONTROLLERS
# ═══════════════════════════════════════════════

class ProductoController(AdminController):
  """CRUD controller for Producto model."""

  model = Producto
  list_fields = ["codigo", "nombre", "precio_unitario", "categoria", "actividad"]
  search_fields = ["codigo", "nombre"]
  filters = {"tipo": ["producto", "servicio"], "categoria": Categoria}

  @auth_required
  def index(self, request):
    query = Producto.where("empresa", current_user.empresa)
    if request.get("search"):
      query = query.where("nombre__ilike", f"%{request.search}%")
    return TableView(
      title="Productos",
      columns=["Código", "Nombre", "Precio", "Categoría"],
      rows=[
        [p.codigo, p.nombre, f"${p.precio_unitario}", p.categoria_id.nombre if p.categoria_id else "-"]
        for p in query.paginate(request.page, 20).all()
      ],
      actions=["create", "edit", "delete", "view"],
    )


class FacturaController(AdminController):
  """CRUD controller for Factura."""

  model = Factura
  list_fields = ["tipo", "folio", "fecha", "cliente", "total", "estatus"]
  detail_fields = ["folio", "fecha", "cliente", "proveedor", "subtotal", "iva", "total", "lineas"]

  @auth_required
  def index(self, request):
    query = Factura.where("empresa", current_user.empresa)
    if request.get("tipo"):
      query = query.where("tipo", request.tipo)
    return TableView(
      title="Facturas",
      columns=["Folio", "Tipo", "Fecha", "Cliente", "Total", "Estatus"],
      rows=[
        [f.folio, f.tipo, f.fecha.strftime("%d/%m/%Y"),
         f.cliente.nombre if f.cliente_id else "-",
         f"${f.total}", f.estatus]
        for f in query.paginate(request.page, 20).all()
      ],
    )


class InventarioController(AdminController):
  """Inventory controller with stock alerts."""

  @auth_required
  def bajo_stock(self, request):
    """Show products below minimum stock."""
    query = Inventario.where("empresa", current_user.empresa)
    query = query.where("stock_actual < stock_minimo")
    query = query.where("stock_minimo > 0")

    return TableView(
      title="Inventario Bajo",
      columns=["Producto", "Almacén", "Stock Actual", "Mínimo"],
      rows=[
        [i.producto_id.nombre, i.almacen_id.nombre if i.almacen_id else "Default",
         str(i.stock_actual), str(i.stock_minimo)]
        for i in query.all()
      ],
    )


class ProyectoController(AdminController):
  """Project management controller."""

  model = Proyecto
  kanban_fields = ["nombre", "estatus", "presupuesto", "fecha_fin"]


class TareasController(AdminController):
  """Task management with Kanban view."""

  model = Tarea

  @auth_required
  def kanban(self, request):
    """Return tasks grouped by status."""
    query = Tarea.where("empresa", current_user.empresa)
    tasks = query.all()

    columns = {
      "pendiente": [],
      "en_progreso": [],
      "completado": [],
    }

    for task in tasks:
      columns[task.estatus].append({
        "id": task.id,
        "titulo": task.titulo,
        "prioridad": task.prioridad,
        "responsable": task.responsable.nombre if task.responsable_id else None,
      })

    return columns


# ═══════════════════════════════════════════════
#  BUSINESS LOGIC SERVICES
# ═══════════════════════════════════════════════

class FacturacionService:
  """Business logic for invoicing."""

  @staticmethod
  def calcular_totales(lineas: list) -> dict:
    """Calculate subtotal, IVA, and total from line items."""
    subtotal = sum(l.total_linea for l in lineas)
    # Assume 16% IVA
    iva = subtotal * 0.16
    total = subtotal + iva
    return {
      "subtotal": round(subtotal, 2),
      "iva": round(iva, 2),
      "total": round(total, 2),
    }

  @staticmethod
  def generar_factura(pedido_id: str) -> Factura:
    """Convert a sales order to an invoice."""
    pedido = Pedido.find(pedido_id)
    if not pedido:
      raise ValueError("Pedido no encontrado")

    # Create invoice
    factura = Factura(
      tipo="venta",
      folio=f"FAC-{pedido.fecha.strftime('%Y%m%d')}-{pedido.id[:8]}",
      cliente=pedido.cliente,
      empresa=pedido.empresa,
    )

    # Copy lines
    for linea in PedidoLinea.where("pedido", pedido.id).all():
      FacturaLinea(
        factura=factura.id,
        producto=linea.producto,
        cantidad=linea.cantidad,
        precio_unitario=linea.precio_unitario,
        total_linea=linea.total_linea,
      ).save()

    # Calculate totals
    lineas = FacturaLinea.where("factura", factura.id).all()
    totales = FacturacionService.calcular_totales(lineas)
    factura.subtotal = totales["subtotal"]
    factura.iva = totales["iva"]
    factura.total = totales["total"]
    factura.estatus = "timbrada"
    factura.save()

    return factura


class InventarioService:
  """Business logic for inventory management."""

  @staticmethod
  def entrada(producto_id: str, cantidad: float, almacen: str = "default") -> None:
    """Register an inventory entry (receipt)."""
    MovimientoInventario(
      tipo="entrada",
      producto=producto_id,
      almacen=almacen,
      cantidad=cantidad,
    ).save()

    inv = Inventario.get(producto=producto_id, almacen=almacen) or Inventario(
      producto=producto_id, almacen=almacen
    )
    inv.stock_actual += cantidad
    inv.save()

  @staticmethod
  def salida(producto_id: str, cantidad: float, almacen: str = "default") -> bool:
    """Register an inventory exit (dispatch). Returns False if not enough stock."""
    inv = Inventario.get(producto=producto_id, almacen=almacen)
    if not inv or inv.stock_actual < cantidad:
      return False

    MovimientoInventario(
      tipo="salida",
      producto=producto_id,
      almacen=almacen,
      cantidad=cantidad,
    ).save()

    inv.stock_actual -= cantidad
    inv.save()
    return True

  @staticmethod
  def transferir(origen: str, destino: str, producto_id: str, cantidad: float) -> bool:
    """Transfer inventory between warehouses."""
    if not InventarioService.salida(producto_id, cantidad, almacen=origen):
      return False
    InventarioService.entrada(producto_id, cantidad, almacen=destino)
    return True

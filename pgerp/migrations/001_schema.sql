-- PyGo ERP Database Schema
-- Migration 001: Core schema

-- Multi-tenancy
CREATE TABLE IF NOT EXISTS empresas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rfc VARCHAR(20) UNIQUE,
  razon_social VARCHAR(200) NOT NULL,
  nombre_comercial VARCHAR(200),
  email VARCHAR(255),
  telefono VARCHAR(50),
  direccion TEXT,
  ciudad VARCHAR(100),
  estado VARCHAR(100),
  codigo_postal VARCHAR(20),
  pais VARCHAR(10) DEFAULT 'MX',
  moneda VARCHAR(3) DEFAULT 'MXN',
  activo BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usuarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(200) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(256) NOT NULL,
  rol VARCHAR(50) DEFAULT 'usuario',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS permisos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo VARCHAR(100) UNIQUE,
  descripcion TEXT,
  roles TEXT[],
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Catalogs
CREATE TABLE IF NOT EXISTS categorias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(100) NOT NULL,
  descripcion TEXT,
  tipo VARCHAR(50) DEFAULT 'producto',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unidades_medida (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clave VARCHAR(20) UNIQUE,
  descripcion VARCHAR(200),
  tipo VARCHAR(50) DEFAULT 'longitud',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS impuestos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo VARCHAR(20) UNIQUE,
  descripcion VARCHAR(200),
  tipo VARCHAR(50) DEFAULT 'iva',
  tasa DECIMAL(5,2) DEFAULT 0,
  activo BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monedas (
  codigo VARCHAR(3) PRIMARY KEY,
  nombre VARCHAR(100),
  simbolo VARCHAR(10),
  tipo_cambio DECIMAL(10,4),
  fecha_tipo_cambio DATE DEFAULT CURRENT_DATE
);

-- Products
CREATE TABLE IF NOT EXISTS productos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo VARCHAR(50),
  nombre VARCHAR(200) NOT NULL,
  descripcion TEXT,
  tipo VARCHAR(50) DEFAULT 'producto',
  categoria UUID REFERENCES categorias(id),
  unidad_medida VARCHAR(20) DEFAULT 'pz',
  precio_unitario DECIMAL(10,2) DEFAULT 0,
  costo DECIMAL(10,2),
  precio_mayoreo DECIMAL(10,2),
  imagen VARCHAR(500),
  stock_minimo DECIMAL(10,3) DEFAULT 0,
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS productos_impuestos (
  producto UUID REFERENCES productos(id) ON DELETE CASCADE,
  impuesto UUID REFERENCES impuestos(id) ON DELETE CASCADE,
  PRIMARY KEY (producto, impuesto)
);

-- Contacts
CREATE TABLE IF NOT EXISTS clientes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(200) NOT NULL,
  rfc VARCHAR(20),
  email VARCHAR(255),
  telefono VARCHAR(50),
  direccion TEXT,
  ciudad VARCHAR(100),
  estado VARCHAR(100),
  pais VARCHAR(10) DEFAULT 'MX',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proveedores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(200) NOT  NULL,
  rfc VARCHAR(20),
  email VARCHAR(255),
  telefono VARCHAR(50),
  direccion TEXT,
  ciudad VARCHAR(100),
  estado VARCHAR(100),
  pais VARCHAR(10) DEFAULT 'MX',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Accounting
CREATE TABLE IF NOT EXISTS cuentas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo VARCHAR(20),
  nombre VARCHAR(200) NOT NULL,
  tipo VARCHAR(50) DEFAULT 'activo',
  naturaleza VARCHAR(10) DEFAULT 'debe',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS facturas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo VARCHAR(50) DEFAULT 'venta',
  folio VARCHAR(50),
  serie VARCHAR(20),
  fecha TIMESTAMP DEFAULT NOW(),
  subtotal DECIMAL(12,2) DEFAULT 0,
  iva DECIMAL(12,2) DEFAULT 0,
  total DECIMAL(12,2) DEFAULT 0,
  cliente UUID REFERENCES clientes(id),
  proveedor UUID REFERENCES proveedores(id),
  estatus VARCHAR(50) DEFAULT 'borrador',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS facturas_lineas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  factura UUID REFERENCES facturas(id) ON DELETE CASCADE,
  producto UUID REFERENCES productos(id),
  cantidad DECIMAL(10,3) DEFAULT 1,
  precio_unitario DECIMAL(10,2) DEFAULT 0,
  descuento DECIMAL(10,2) DEFAULT 0,
  total_linea DECIMAL(12,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pagos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo VARCHAR(50) DEFAULT 'efectivo',
  monto DECIMAL(12,2) DEFAULT 0,
  fecha TIMESTAMP DEFAULT NOW(),
  factura UUID REFERENCES facturas(id),
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Inventory
CREATE TABLE IF NOT EXISTS almacenes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(100) NOT NULL,
  direccion TEXT,
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  producto UUID REFERENCES productos(id),
  almacen UUID REFERENCES almacenes(id),
  stock_actual DECIMAL(12,3) DEFAULT 0,
  stock_minimo DECIMAL(12,3) DEFAULT 0,
  ubicacion VARCHAR(100),
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS movimientos_inventario (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo VARCHAR(50) DEFAULT 'entrada',
  producto UUID REFERENCES productos(id),
  almacen UUID REFERENCES almacenes(id),
  cantidad DECIMAL(12,3) DEFAULT 1,
  fecha TIMESTAMP DEFAULT NOW(),
  documento UUID,
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Sales
CREATE TABLE IF NOT EXISTS pedidos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo VARCHAR(50) DEFAULT 'pedido',
  folio VARCHAR(50),
  fecha TIMESTAMP DEFAULT NOW(),
  cliente UUID REFERENCES clientes(id),
  subtotal DECIMAL(12,2) DEFAULT 0,
  iva DECIMAL(12,2) DEFAULT 0,
  total DECIMAL(12,2) DEFAULT 0,
  estatus VARCHAR(50) DEFAULT 'borrador',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pedidos_lineas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pedido UUID REFERENCES pedidos(id) ON DELETE CASCADE,
  producto UUID REFERENCES productos(id),
  cantidad DECIMAL(10,3) DEFAULT 1,
  precio_unitario DECIMAL(10,2) DEFAULT 0,
  total_linea DECIMAL(12,2) DEFAULT 0
);

-- Purchasing
CREATE TABLE IF NOT EXISTS ordenes_compra (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  folio VARCHAR(50),
  fecha TIMESTAMP DEFAULT NOW(),
  proveedor UUID REFERENCES proveedores(id),
  subtotal DECIMAL(12,2) DEFAULT 0,
  iva DECIMAL(12,2) DEFAULT 0,
  total DECIMAL(12,2) DEFAULT 0,
  estatus VARCHAR(50) DEFAULT 'borrador',
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ordenes_compra_lineas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  orden UUID REFERENCES ordenes_compra(id) ON DELETE CASCADE,
  producto UUID REFERENCES productos(id),
  cantidad DECIMAL(10,3) DEFAULT 1,
  precio_unitario DECIMAL(10,2) DEFAULT 0,
  total_linea DECIMAL(12,2) DEFAULT 0
);

-- HR
CREATE TABLE IF NOT EXISTS departamentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(100) NOT NULL,
  gerente UUID REFERENCES empleados(id),
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS puestos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(100) NOT NULL,
  descripcion TEXT,
  salario_min DECIMAL(12,2),
  salario_max DECIMAL(12,2),
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS empleados (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario UUID REFERENCES usuarios(id),
  nombre VARCHAR(200) NOT NULL,
  apellidos VARCHAR(200),
  fecha_nacimiento DATE,
  fecha_ingreso DATE DEFAULT CURRENT_DATE,
  departamento UUID REFERENCES departamentos(id),
  puesto UUID REFERENCES puestos(id),
  salario DECIMAL(12,2),
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Projects
CREATE TABLE IF NOT EXISTS proyectos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(200) NOT NULL,
  descripcion TEXT,
  cliente UUID REFERENCES clientes(id),
  fecha_inicio DATE,
  fecha_fin DATE,
  estatus VARCHAR(50) DEFAULT 'activo',
  presupuesto DECIMAL(12,2),
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tareas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  proyecto UUID REFERENCES proyectos(id),
  titulo VARCHAR(200) NOT NULL,
  descripcion TEXT,
  responsable UUID REFERENCES empleados(id),
  fecha_inicio DATE,
  fecha_fin DATE,
  estatus VARCHAR(50) DEFAULT 'pendiente',
  prioridad VARCHAR(50) DEFAULT 'normal',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS timesheets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tarea UUID REFERENCES tareas(id),
  empleado UUID REFERENCES empleados(id),
  fecha DATE DEFAULT CURRENT_DATE,
  horas DECIMAL(5,2) DEFAULT 0,
  descripcion TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Config
CREATE TABLE IF NOT EXISTS configuraciones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  llave VARCHAR(100) NOT NULL,
  valor TEXT,
  empresa UUID REFERENCES empresas(id),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (llave, empresa)
);

-- Indexes
CREATE INDEX idx_productos_empresa ON productos(empresa);
CREATE INDEX idx_facturas_empresa ON facturas(empresa);
CREATE INDEX idx_facturas_cliente ON facturas(cliente);
CREATE INDEX idx_facturas_fecha ON facturas(fecha);
CREATE INDEX idx_pedidos_empresa ON pedidos(empresa);
CREATE INDEX idx_pedidos_estatus ON pedidos(estatus);
CREATE INDEX idx_inventarios_producto ON inventarios(producto);
CREATE INDEX idx_inventarios_almacen ON inventarios(almacen);
CREATE INDEX idx_clientes_empresa ON clientes(empresa);
CREATE INDEX idx_empleados_empresa ON empleados(empresa);

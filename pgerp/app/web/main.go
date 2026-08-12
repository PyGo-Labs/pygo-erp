// Package main — PyGo ERP entry point (Go web orchestrator layer).
// Starts the Go HTTP server, initializes the UDS bridge to Python,
// and serves routes. Python handles all business logic via app.Call().
package main

import (
	"log"
	"net/http"
	"os"

	"pygo-framework/web"
)

func main() {
	socketPath := "/tmp/pgerp.sock"
	os.MkdirAll("/tmp", 0o755)

	app := web.NewApp(socketPath, "app.core.main")
	if err := app.Init(); err != nil {
		log.Fatalf("PyGo init error: %v", err)
	}

	registerRoutes(app)

	log.Println("PyGo ERP — dual-language architecture ready")
	log.Println("  Go:    HTTP server on :8080")
	log.Printf("  Python: UDS bridge at %s\n", socketPath)

	if err := app.Run(":8080"); err != nil {
		log.Fatalf("PyGo server error: %v", err)
	}
}

func registerRoutes(app *web.App) {
	r := app.Router()

	// --- Go-native routes (no Python bridge needed) ---

	r.Handle("GET", "/health", func(ctx map[string]interface{}) (interface{}, error) {
		return map[string]interface{}{
			"status":    "ok",
			"runtime":   "hybrid",
			"languages": []string{"go", "python"},
		}, nil
	}, false, false)

	r.Handle("GET", "/", func(ctx map[string]interface{}) (interface{}, error) {
		html := `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>PyGo ERP — Native Dual-Language</title>
  <script src="https://unpkg.com/htmx.org@2.0.1"></script>
  <script src="https://unpkg.com/alpinejs@3.13.0/dist/cdn.min.js" defer></script>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
  <div class="container mx-auto p-6">
    <h1 class="text-3xl font-bold text-blue-600 mb-4">PyGo ERP</h1>
    <p class="text-gray-600 mb-4">Dual-Language Architecture — Go + Python</p>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Productos</h3>
        <p class="text-2xl text-blue-600" id="productos-count">Cargando...</p>
      </div>
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Clientes</h3>
        <p class="text-2xl text-green-600" id="clientes-count">Cargando...</p>
      </div>
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Facturas</h3>
        <p class="text-2xl text-yellow-600" id="facturas-count">Cargando...</p>
      </div>
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Status</h3>
        <p class="text-2xl text-purple-600">Active</p>
      </div>
    </div>
  </div>
</body>
</html>`
		return html, nil
	}, false, false)

	// --- REST API routes (delegate to Python handlers via bridge) ---

	// GET /api/productos — lista productos
	r.Handle("GET", "/api/productos", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.list", map[string]interface{}{})
	}, true, false)

	// POST /api/productos — crea un producto
	r.Handle("POST", "/api/productos", func(ctx map[string]interface{}) (interface{}, error) {
		nombre, _ := ctx["nombre"].(string)
		precio, _ := ctx["precio"].(float64)
		return app.Call("core.services.productos.create", map[string]interface{}{
			"nombre": nombre,
			"precio": precio,
		})
	}, true, false)

	// GET /api/clientes — lista clientes
	r.Handle("GET", "/api/clientes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.list", map[string]interface{}{})
	}, true, false)

	// GET /api/facturas — lista facturas
	r.Handle("GET", "/api/facturas", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.list", map[string]interface{}{})
	}, true, false)

	// --- HTML views (HTMX + pygo-ui components) ---

	r.Handle("GET", "/productos", func(ctx map[string]interface{}) (interface{}, error) {
		// Fetch data from Python, render HTML template
		result, err := app.Call("core.services.productos.list", map[string]interface{}{})
		if err != nil {
			return nil, err
		}
		html := renderProductosTable(result)
		return html, nil
	}, false, false)
}

// renderProductosTable renders an HTMX-compatible table using pygo-ui components.
func renderProductosTable(data interface{}) string {
	html := `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Productos — PyGo ERP</title>
  <script src="https://unpkg.com/htmx.org@2.0.1"></script>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
  <div class="container mx-auto p-6">
    <div class="flex justify-between items-center mb-4">
      <h1 class="text-2xl font-bold text-blue-600">Productos</h1>
      <button class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded"
              hx-post="/api/productos"
              hx-include="#new-product-form">
        Nuevo Producto
      </button>
    </div>
    <div class="bg-white rounded shadow overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nombre</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Precio</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>`
	return html
}

var _ = http.StatusOK

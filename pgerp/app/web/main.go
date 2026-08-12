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
	// UDS socket path for Go↔Python communication
	socketPath := "/tmp/pgerp.sock"
	os.MkdirAll("/tmp", 0o755)

	// Initialize Go web app with Python bridge
	// Python module path: "app.core.main"
	app := web.NewApp(socketPath, "app.core.main")
	if err := app.Init(); err != nil {
		log.Fatalf("PyGo init error: %v", err)
	}

	// Register routes — delegate to Python handlers via app.Call()
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

	// GET /health — Go native health check
	r.Handle("GET", "/health", func(ctx map[string]interface{}) (interface{}, error) {
		return map[string]interface{}{"status": "ok", "runtime": "hybrid", "languages": []string{"go", "python"}}, nil
	}, false, false)

	// GET / — ERP dashboard
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
    <p class="text-gray-600">Dual-Language Architecture — Go + Python</p>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Productos</h3>
        <p class="text-2xl text-blue-600" id="productos-count">0</p>
      </div>
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Clientes</h3>
        <p class="text-2xl text-green-600" id="clientes-count">0</p>
      </div>
      <div class="bg-white p-4 rounded shadow">
        <h3 class="font-semibold text-gray-700">Facturas</h3>
        <p class="text-2xl text-yellow-600" id="facturas-count">0</p>
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
}

// http is used for default values
var _ = http.StatusOK

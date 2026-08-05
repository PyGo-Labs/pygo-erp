// Package main — PyGo ERP entry point (Go web orchestrator layer).
// Starts the Go HTTP server, initializes the UDS bridge to Python,
// and serves routes. Python handles all business logic via app.Call().
package main

import (
	"log"
	"os"

	"pygo-framework/web"
)

func main() {
	// UDS socket path for Go↔Python communication
	socketPath := "/tmp/pgerp.sock"
	os.MkdirAll("storage", 0o755)

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
	_ = app
	// Routes will be added via app.Get/Post when we wire handlers
}

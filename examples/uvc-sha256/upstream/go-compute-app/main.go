package main

import (
	"crypto/sha256"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
)

// The computeHandler performs a CPU-intensive hashing loop.
func computeHandler(w http.ResponseWriter, r *http.Request) {
	// Allow the number of iterations to be configurable via query param
	iterations, err := strconv.Atoi(r.URL.Query().Get("iter"))
	if err != nil || iterations <= 0 {
		iterations = 20000 // A default value if not specified
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Cannot read body", http.StatusBadRequest)
		return
	}

	// The CPU-bound work: hash the data repeatedly
	hash := sha256.Sum256(body)
	for i := 0; i < iterations-1; i++ {
		hash = sha256.Sum256(hash[:])
	}

	// Send back the final hash as proof of work
	fmt.Fprintf(w, "%x", hash)
}

func main() {
	// We only need the compute handler for this test
	http.HandleFunc("/compute", computeHandler)

	log.Println("Starting Go COMPUTE server on port 8080...")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatalf("Could not start server: %s\n", err)
	}
}

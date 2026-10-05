// uvc-server runs on edge server nodes. It keeps the upstream /compute API
// and adds the server-side compute time as a response header.
package main

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"uvc-sha256/internal/work"
)

func computeHandler(w http.ResponseWriter, r *http.Request) {
	iter, err := strconv.Atoi(r.URL.Query().Get("iter"))
	if err != nil || iter <= 0 {
		iter = work.DefaultIter
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Cannot read body", http.StatusBadRequest)
		return
	}

	start := time.Now()
	h := work.Hash(body, iter)
	elapsed := time.Since(start)

	// Lets the client split TCT into compute time and network/queueing time.
	w.Header().Set("X-Compute-Us", strconv.FormatInt(elapsed.Microseconds(), 10))
	w.Header().Set("X-Server", hostname)
	fmt.Fprintf(w, "%x", h)
}

var hostname, _ = os.Hostname()

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/compute", computeHandler)
	http.HandleFunc("/hello", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "Hello from Go!")
	})

	log.Printf("uvc-server (%s) listening on :%s", hostname, port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Could not start server: %s\n", err)
	}
}

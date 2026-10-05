package main

import (
	"fmt"
	"log"
	"net/http"
	"time"
)

func main() {
	// THIS IS THE KEY LINE: Print Unix time in nanoseconds and flush stdout.
	fmt.Println(time.Now().UnixNano())

	// Your original server code
	http.HandleFunc("/hello", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "Hello from Go!")
	})

	log.Println("Starting Go server on port 8080...")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatalf("Could not start server: %s\n", err)
	}
}

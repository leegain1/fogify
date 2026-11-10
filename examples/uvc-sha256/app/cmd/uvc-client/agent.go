package main

// agent mode: an HTTP server on the local node so that an external driver can
// pick the execution location per task.
//
//	uvc-client agent [-listen :8081] [-servers edge1=http://edge-server-1:8080,edge2=http://edge-server-2:8080]
//
//	POST /run?target=local|edge1|edge2&iter=N&payload=B
//	     -> {"target","tct_ms","server_compute_ms","status","ts_unix_ms"}
//	GET  /probe?target=edge1    -> {"rtt_ms"}  (HTTP GET /hello round trip, for RTT observation)
//
// Tasks are executed one at a time (like `run`), and TCT is measured here,
// so the driver's own latency is not part of TCT.

import (
	"encoding/json"
	"flag"
	"io"
	"log"
	"math/rand"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

type agent struct {
	servers  map[string]string
	client   *http.Client
	mu       sync.Mutex // one task at a time
	payloads map[int][]byte
}

func runAgent(args []string) {
	fs := flag.NewFlagSet("agent", flag.ExitOnError)
	listen := fs.String("listen", ":8081", "listen address")
	servers := fs.String("servers", "edge1=http://edge-server-1:8080,edge2=http://edge-server-2:8080",
		"name=url pairs of edge servers")
	fs.Parse(args)

	a := &agent{
		servers:  map[string]string{},
		client:   &http.Client{Timeout: 60 * time.Second},
		payloads: map[int][]byte{},
	}
	for _, kv := range strings.Split(*servers, ",") {
		if p := strings.SplitN(strings.TrimSpace(kv), "=", 2); len(p) == 2 {
			a.servers[p[0]] = strings.TrimRight(p[1], "/")
		}
	}
	http.HandleFunc("/run", a.handleRun)
	http.HandleFunc("/probe", a.handleProbe)
	log.Printf("uvc-client agent listening on %s, servers %v", *listen, a.servers)
	log.Fatal(http.ListenAndServe(*listen, nil))
}

func (a *agent) payload(n int) []byte {
	if p, ok := a.payloads[n]; ok {
		return p
	}
	p := make([]byte, n)
	rand.New(rand.NewSource(1)).Read(p)
	a.payloads[n] = p
	return p
}

func (a *agent) handleRun(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	target := q.Get("target")
	iter, _ := strconv.Atoi(q.Get("iter"))
	size, err := strconv.Atoi(q.Get("payload"))
	if err != nil || size < 0 {
		size = 1024
	}

	c := config{mode: "local", iter: iter}
	url := "local"
	if target != "local" {
		u, ok := a.servers[target]
		if !ok {
			http.Error(w, "unknown target "+target, http.StatusBadRequest)
			return
		}
		c.mode, url = "edge-server", u
	}

	a.mu.Lock()
	payload := a.payload(size)
	start := time.Now()
	serverUs, _, status := runTask(c, a.client, url, payload)
	tct := time.Since(start)
	a.mu.Unlock()

	out := map[string]any{"target": target, "tct_ms": float64(tct.Microseconds()) / 1000,
		"status": status, "ts_unix_ms": start.UnixMilli()}
	if serverUs >= 0 {
		out["server_compute_ms"] = float64(serverUs) / 1000
	}
	writeJSON(w, out)
}

func (a *agent) handleProbe(w http.ResponseWriter, r *http.Request) {
	u, ok := a.servers[r.URL.Query().Get("target")]
	if !ok {
		http.Error(w, "unknown target", http.StatusBadRequest)
		return
	}
	start := time.Now()
	resp, err := a.client.Get(u + "/hello")
	if err != nil {
		writeJSON(w, map[string]any{"error": err.Error()})
		return
	}
	io.Copy(io.Discard, resp.Body) // drain so the keep-alive connection is reused (else RTT x2)
	resp.Body.Close()
	writeJSON(w, map[string]any{"rtt_ms": float64(time.Since(start).Microseconds()) / 1000})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

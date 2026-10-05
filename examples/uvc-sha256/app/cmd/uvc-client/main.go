// uvc-client runs on the local (device) node and measures TCT (Task Completion Time)
// for the same SHA-256 task either computed locally or offloaded to edge servers.
//
//	uvc-client idle                       keep the container alive (default CMD)
//	uvc-client run -mode local ...        compute on this node
//	uvc-client run -mode edge-server ...  POST to -servers (round-robin)
//
// One CSV row per task is written to stdout, so results can be collected with
// `docker exec <container> uvc-client run ...` from the notebook.
package main

import (
	"bytes"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"uvc-sha256/internal/work"
)

// Fogify's agent reads custom metrics from this path inside the container
// (utils/monitoring.py: <container root>/fogify/metrics) and keeps only integer values.
const metricsPath = "/fogify/metrics"

type config struct {
	mode      string
	servers   []string
	iter      int
	payload   int
	n         int
	warmup    int
	interval  time.Duration
	label     string
	seed      int64
	keepalive bool
	verify    bool
	header    bool
}

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	switch os.Args[1] {
	case "idle":
		// Block until the container is stopped (a bare select{} would trip Go's deadlock detector).
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT)
		<-sig
	case "run":
		run(parseRun(os.Args[2:]))
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: uvc-client idle | uvc-client run -mode local|edge-server [flags]")
	os.Exit(2)
}

func parseRun(args []string) config {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	var c config
	var servers string
	fs.StringVar(&c.mode, "mode", "local", "local | edge-server")
	fs.StringVar(&servers, "servers", "http://edge-server-1:8080", "comma-separated edge server base URLs (round-robin)")
	fs.IntVar(&c.iter, "iter", 100000, "SHA-256 iterations per task")
	fs.IntVar(&c.payload, "payload", 1024, "payload size in bytes")
	fs.IntVar(&c.n, "n", 20, "number of recorded tasks")
	fs.IntVar(&c.warmup, "warmup", 1, "tasks run before recording (not written)")
	fs.DurationVar(&c.interval, "interval", 0, "pause between tasks, e.g. 100ms")
	fs.StringVar(&c.label, "label", "", "free-form experiment tag written to every row")
	fs.Int64Var(&c.seed, "seed", 1, "payload random seed")
	fs.BoolVar(&c.keepalive, "keepalive", true, "reuse TCP connections (false = new connection per task)")
	fs.BoolVar(&c.verify, "verify", false, "edge-server mode: also compute locally and check the returned hash")
	fs.BoolVar(&c.header, "header", true, "print CSV header")
	fs.Parse(args)

	if c.mode != "local" && c.mode != "edge-server" {
		log.Fatalf("unknown -mode %q (want local or edge-server)", c.mode)
	}
	for _, s := range strings.Split(servers, ",") {
		if s = strings.TrimSpace(s); s != "" {
			c.servers = append(c.servers, strings.TrimRight(s, "/"))
		}
	}
	return c
}

func run(c config) {
	payload := make([]byte, c.payload)
	rand.New(rand.NewSource(c.seed)).Read(payload)

	client := &http.Client{
		Timeout:   60 * time.Second,
		Transport: &http.Transport{DisableKeepAlives: !c.keepalive},
	}

	w := csv.NewWriter(os.Stdout)
	if c.header {
		w.Write([]string{"ts_unix_ms", "label", "mode", "target", "task", "iter", "payload_bytes",
			"tct_ms", "server_compute_ms", "status"})
	}

	var sumUs int64
	for i := -c.warmup; i < c.n; i++ {
		target := "local"
		if c.mode == "edge-server" {
			target = c.servers[(i+c.warmup)%len(c.servers)]
		}

		start := time.Now()
		serverUs, result, status := runTask(c, client, target, payload)
		tct := time.Since(start)

		// Checked after timing so verification does not inflate TCT.
		if c.verify && status == "ok" && result != hex.EncodeToString(expected(payload, c.iter)) {
			status = "hash-mismatch"
		}

		if i >= 0 {
			serverMs := ""
			if serverUs >= 0 {
				serverMs = fmtMs(time.Duration(serverUs) * time.Microsecond)
			}
			w.Write([]string{
				strconv.FormatInt(start.UnixMilli(), 10), c.label, c.mode, target, strconv.Itoa(i),
				strconv.Itoa(c.iter), strconv.Itoa(c.payload), fmtMs(tct), serverMs, status,
			})
			w.Flush()

			sumUs += tct.Microseconds()
			writeMetrics(c.mode, tct.Microseconds(), sumUs/int64(i+1), int64(i+1))
		}
		if c.interval > 0 {
			time.Sleep(c.interval)
		}
	}
}

// runTask performs one task and returns the server-side compute time in µs
// (-1 if not applicable), the hex result, and a status string.
func runTask(c config, client *http.Client, target string, payload []byte) (int64, string, string) {
	if c.mode == "local" {
		h := work.Hash(payload, c.iter)
		return -1, hex.EncodeToString(h[:]), "ok"
	}

	u := target + "/compute?iter=" + url.QueryEscape(strconv.Itoa(c.iter))
	resp, err := client.Post(u, "application/octet-stream", bytes.NewReader(payload))
	if err != nil {
		return -1, "", "error:" + err.Error()
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return -1, "", "error:" + err.Error()
	}
	if resp.StatusCode != http.StatusOK {
		return -1, "", "http:" + strconv.Itoa(resp.StatusCode)
	}

	serverUs, err := strconv.ParseInt(resp.Header.Get("X-Compute-Us"), 10, 64)
	if err != nil {
		serverUs = -1
	}
	return serverUs, string(bytes.TrimSpace(body)), "ok"
}

func expected(payload []byte, iter int) []byte {
	h := work.Hash(payload, iter)
	return h[:]
}

func fmtMs(d time.Duration) string {
	return strconv.FormatFloat(float64(d.Microseconds())/1000, 'f', 3, 64)
}

// writeMetrics exposes the latest TCT to Fogify's monitoring (integers only).
// Failures are ignored: the CSV on stdout is the primary result.
func writeMetrics(mode string, lastUs, avgUs, count int64) {
	m := map[string]int64{
		"tct_us_last": lastUs,
		"tct_us_avg":  avgUs,
		"tasks_done":  count,
	}
	if mode == "local" {
		m["mode_edge_server"] = 0
	} else {
		m["mode_edge_server"] = 1
	}
	data, _ := json.Marshal(m)
	tmp := filepath.Join(filepath.Dir(metricsPath), ".metrics.tmp")
	if os.WriteFile(tmp, data, 0o644) == nil {
		os.Rename(tmp, metricsPath)
	}
}

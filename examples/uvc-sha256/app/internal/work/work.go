// Package work holds the CPU-bound task shared by the local client and the edge server,
// so both modes run exactly the same computation.
package work

import "crypto/sha256"

// DefaultIter matches the default of the upstream go-compute-app.
const DefaultIter = 20000

// Hash hashes data once, then re-hashes the digest iter-1 more times
// (same loop as upstream go-compute-app/main.go).
func Hash(data []byte, iter int) [32]byte {
	if iter <= 0 {
		iter = DefaultIter
	}
	h := sha256.Sum256(data)
	for i := 0; i < iter-1; i++ {
		h = sha256.Sum256(h[:])
	}
	return h
}

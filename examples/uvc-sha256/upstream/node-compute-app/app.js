const http = require('http');
const crypto = require('crypto');
const { URL } = require('url');

const server = http.createServer((req, res) => {
  // Simple router for our compute endpoint
  if (req.url.startsWith('/compute')) {
    const requestUrl = new URL(req.url, `http://${req.headers.host}`);
    const iterations = parseInt(requestUrl.searchParams.get('iter')) || 20000;

    const body = [];
    req.on('data', (chunk) => {
      body.push(chunk);
    });

    req.on('end', () => {
      const bufferBody = Buffer.concat(body);

      // The CPU-bound work: hash the data repeatedly
      let hash = crypto.createHash('sha256').update(bufferBody).digest();
      for (let i = 0; i < iterations - 1; i++) {
        hash = crypto.createHash('sha256').update(hash).digest();
      }

      // Send back the final hash as proof of work
      res.end(hash.toString('hex'));
    });

  } else {
    res.statusCode = 404;
    res.end('Not Found');
  }
});

server.listen(8080, () => {
  console.log('Starting Node.js COMPUTE server on port 8080...');
});

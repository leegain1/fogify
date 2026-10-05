// Load the built-in http module
const http = require('http');

// Define the server's host and port
const host = '0.0.0.0'; // Listen on all network interfaces
const port = 8080;

// Create a request listener function. This runs for every incoming request.
const requestListener = function (req, res) {
    // Check if the request is for the /hello endpoint
    if (req.url === '/hello') {
        res.writeHead(200); // Set the status code to 200 (OK)
        res.end('Hello from Node.js!'); // Send the response and close the connection
    } else {
        // If it's any other URL, send a 404 Not Found error
        res.writeHead(404);
        res.end('Not Found');
    }
};

// Create the server instance
const server = http.createServer(requestListener);

// Start listening for requests
server.listen(port, host, () => {
    console.log(`Node.js server is running on http://${host}:${port}`);
});

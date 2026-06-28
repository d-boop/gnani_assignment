const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;

const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.json': 'application/json'
};

const server = http.createServer((req, res) => {
  console.log(`${req.method} ${req.url}`);

  // Normalize URL path
  let filePath = req.url === '/' 
    ? path.join(__dirname, 'index.html') 
    : path.join(__dirname, req.url);

  // Get file extension
  const ext = path.extname(filePath);
  let contentType = MIME_TYPES[ext] || 'application/octet-stream';

  // Read file from disk
  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT') {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('404 Not Found');
      } else {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        res.end(`Internal Server Error: ${err.code}`);
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content, 'utf-8');
    }
  });
});

// A simple log for WebSocket connections
server.on('upgrade', (req, socket, head) => {
  console.log(`[Upgrade Request] WS attempt on path: ${req.url}`);
  // Since we are running the frontend standalone right now, we let the client
  // drop back to Mock/Simulation mode when the WebSocket fails to connect or we can close the socket.
  socket.write(
    'HTTP/1.1 400 Bad Request\r\n' +
    'Connection: close\r\n' +
    'Content-Type: text/plain\r\n' +
    '\r\n' +
    'Please connect your WebSocket client directly to the backend translation server.'
  );
  socket.destroy();
});

server.listen(PORT, () => {
  console.log(`==================================================`);
  console.log(`AuraTranslate static dev server running at:`);
  console.log(`http://localhost:${PORT}`);
  console.log(`==================================================`);
  console.log(`NOTE: Microphone access (getUserMedia) requires a`);
  console.log(`secure context. Accessing via http://localhost:${PORT}`);
  console.log(`is permitted by modern browsers.`);
  console.log(`==================================================`);
});

import express from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import httpProxy from 'http-proxy';
import { initDatabase } from './db/init.js';
import { setupSocketHandlers } from './socket/handler.js';
import { startCleanupCron } from './cron/cleanup.js';
import authRoutes from './routes/auth.js';
import roomRoutes, { setRoomsIo } from './routes/rooms.js';
import uploadRoutes from './routes/upload.js';
import apiRoutes, { setIoInstance } from './routes/api.js';
import filesRoutes from './routes/files.js';
import { setPollerIo, startAllWatchers } from './services/web-poller.js';
import { setupTerminalWebSocket, OPENCODE_HTML } from './terminal.js';
import type { ClientToServerEvents, ServerToClientEvents } from '../../shared/types.js';

// Proxy for ClaudeCodeWrapper (port 8000) served under /claude
const cwProxy = httpProxy.createProxyServer({ target: 'http://localhost:8000', ws: true });
cwProxy.on('error', (_err, _req, res) => {
  if ('writeHead' in res) {
    (res as any).writeHead(502);
    (res as any).end('ClaudeCodeWrapper unavailable');
  }
});

async function main() {
  await initDatabase();

  const app = express();
  const server = createServer(app);

  // Terminal WebSocket must be set up BEFORE Socket.IO to ensure its upgrade
  // handler runs first (Socket.IO destroys non-matching upgrade sockets).
  setupTerminalWebSocket(server);

  // Proxy /claude/ws WebSocket upgrades to ClaudeCodeWrapper
  server.on('upgrade', (req, socket, head) => {
    if (req.url?.startsWith('/claude/ws')) {
      req.url = '/ws';
      cwProxy.ws(req, socket, head);
    }
  });

  const io = new Server<ClientToServerEvents, ServerToClientEvents>(server, {
    cors: {
      origin: '*',
      methods: ['GET', 'POST'],
    },
    maxHttpBufferSize: 100 * 1024 * 1024,
  });

  app.set('trust proxy', true);
  app.use(cors());
  app.use(express.json({ limit: '100mb' }));
  app.use(express.urlencoded({ extended: true, limit: '100mb' }));

  // Static files for chat uploads
  app.use('/uploads', express.static(path.join(__dirname, '..', 'uploads')));

  // API Routes
  app.use('/auth', authRoutes);
  app.use('/rooms', roomRoutes);
  app.use('/upload', uploadRoutes);
  app.use('/api', apiRoutes);
  app.use('/files', filesRoutes);

  // Health check
  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });

  // ClaudeCodeWrapper proxy: /claude → localhost:8000
  // Express strips the /claude prefix, so req.url inside the handler is relative to 8000's root
  app.use('/claude', (req, res) => { cwProxy.web(req, res); });

  // OpenCode Terminal: /opencode
  app.get('/opencode', (_req, res) => { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.send(OPENCODE_HTML); });
  app.get('/opencode/', (_req, res) => { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.send(OPENCODE_HTML); });

  // Serve the web client
  const clientDistPath = path.join(__dirname, '..', '..', 'client', 'dist-web');
  if (fs.existsSync(clientDistPath)) {
    app.use(express.static(clientDistPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(clientDistPath, 'index.html'));
    });
  }

  // Socket.IO
  setupSocketHandlers(io);
  setIoInstance(io);
  setRoomsIo(io);
  setPollerIo(io);

  // Start web watchers and cleanup cron
  startAllWatchers();
  startCleanupCron();

  const PORT = Number(process.env.PORT) || 3000;

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`Messenger: 심심이 Server running on port ${PORT}`);
    console.log(`  Local:   http://localhost:${PORT}`);
    console.log(`  Network: http://0.0.0.0:${PORT}`);
  });
}

main().catch(console.error);

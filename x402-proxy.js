/**
 * x402 Payment Proxy for CodeShot API.
 * Thin proxy that handles x402 payment verification, then forwards to Python backend.
 * Reference implementation using @x402/express middleware.
 */
const express = require('express');
const { paymentMiddleware } = require('@x402/express');
const http = require('node:http');

const PORT = process.env.X402_PORT || 8100;
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const PAY_TO = process.env.EVM_PAYEE_ADDRESS || '0xed6881b56690C26189d914F2302C9af79685CB97';
const DOMAIN = process.env.DOMAIN || 'https://drmadmeow.up.railway.app';

const app = express();

// CORS
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, PAYMENT-SIGNATURE, SIGN-IN-WITH-X, PAYMENT-REQUIRED');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Expose-Headers', 'PAYMENT-REQUIRED, PAYMENT-SIGNATURE, SIGN-IN-WITH-X');
  if (req.method === 'OPTIONS') return res.sendStatus(200);
  next();
});

// x402 payment middleware for agent endpoints
app.use('/v1/agent', paymentMiddleware({
  'POST /screenshot': {
    accepts: [{ scheme: 'exact', network: 'eip155:8453', price: '0.01', payTo: PAY_TO }],
    description: 'Generate a code screenshot as PNG',
  },
  'POST /diff': {
    accepts: [{ scheme: 'exact', network: 'eip155:8453', price: '0.01', payTo: PAY_TO }],
    description: 'Generate a code diff as PNG',
  },
  'POST /animate': {
    accepts: [{ scheme: 'exact', network: 'eip155:8453', price: '0.05', payTo: PAY_TO }],
    description: 'Generate an animated code screenshot',
  },
  'POST /annotate': {
    accepts: [{ scheme: 'exact', network: 'eip155:8453', price: '0.03', payTo: PAY_TO }],
    description: 'Generate AI-annotated code screenshot',
  },
}));

// Proxy paid requests to Python backend
app.post('/v1/agent/:path', async (req, res) => {
  const realPath = `/v1/${req.params.path}`;
  
  const options = {
    hostname: '127.0.0.1',
    port: 8000,
    path: realPath,
    method: 'POST',
    headers: {
      'Content-Type': req.headers['content-type'] || 'application/json',
    },
  };

  const proxy = http.request(options, (backendRes) => {
    backendRes.pipe(res);
    res.status(backendRes.statusCode);
  });

  proxy.on('error', (err) => {
    res.status(502).json({ error: 'Backend unavailable' });
  });

  req.pipe(proxy);
});

// Health
app.get('/health', (req, res) => res.json({ status: 'ok', proxy: 'x402' }));

// Favicon
app.get('/favicon.ico', (req, res) => res.status(204).end());

// Discovery
app.get('/.well-known/x402', (req, res) => {
  res.json({
    version: 1,
    resources: [
      `${DOMAIN}/v1/agent/screenshot`,
      `${DOMAIN}/v1/agent/diff`,
      `${DOMAIN}/v1/agent/animate`,
      `${DOMAIN}/v1/agent/annotate`,
    ],
  });
});

app.listen(PORT, () => {
  console.log(`x402 proxy listening on :${PORT}, backend at ${BACKEND}`);
});

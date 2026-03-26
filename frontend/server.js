// Production server: serves the SPA and proxies /api/* to the backend.
// Used by Azure App Service; NOT used during local development (vite dev handles it).

const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");
const path = require("path");

const PORT = process.env.PORT || 8080;
const BACKEND_URL =
  process.env.BACKEND_URL || "https://cronosaurus-backend.azurewebsites.net";

const app = express();

// Proxy /api requests to the backend
app.use(
  "/api",
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    // Forward Easy Auth headers to the backend
    onProxyReq(proxyReq, req) {
      const headers = [
        "x-ms-client-principal",
        "x-ms-client-principal-id",
        "x-ms-client-principal-name",
        "x-ms-token-google-access-token",
        "cookie",
      ];
      for (const h of headers) {
        if (req.headers[h]) {
          proxyReq.setHeader(h, req.headers[h]);
        }
      }
    },
  })
);

// Serve static SPA files
app.use(express.static(path.join(__dirname, "dist")));

// SPA fallback — all non-API, non-static routes serve index.html
app.get("*", (_req, res) => {
  res.sendFile(path.join(__dirname, "dist", "index.html"));
});

app.listen(PORT, () => {
  console.log(`Frontend server listening on port ${PORT}`);
});

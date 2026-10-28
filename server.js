require("dotenv").config();

const express = require("express");
const cors = require("cors");
const { connectDB, closeDB } = require("./config/db");
const collectorRoutes = require("./routes/collector");
const internalRoutes = require("./routes/internal");

const app = express();
app.use(cors());
app.use("/internal", internalRoutes);
app.use(express.json({ limit: "1mb" }));
app.get("/", (_req, res) => res.json({ status: "BugScope AI backend is running" }));
app.use("/api", collectorRoutes);

const PORT = process.env.PORT || 5000;
let server;
async function start() {
  await connectDB();
  server = app.listen(PORT, () => console.log(`[server] BugScope AI backend listening on port ${PORT}`));
}
async function shutdown(signal) {
  console.log(`[server] received ${signal}; shutting down`);
  if (server) await new Promise((resolve) => server.close(resolve));
  await closeDB();
}
process.once("SIGINT", () => shutdown("SIGINT").finally(() => process.exit(0)));
process.once("SIGTERM", () => shutdown("SIGTERM").finally(() => process.exit(0)));

if (require.main === module) start().catch((error) => {
  console.error(`[server] startup failed (${error.code || error.name}): ${error.message}`);
  closeDB().finally(() => { process.exitCode = 1; });
});

module.exports = { app, start };

require("dotenv").config();
const express = require("express");
const cors = require("cors");

const connectDB = require("./config/db");
const collectorRoutes = require("./routes/collector");

const app = express();

app.use(cors());
app.use(express.json());

app.get("/", (_req, res) => {
  res.json({ status: "BugScope AI backend is running" });
});

app.use("/api", collectorRoutes);

const PORT = process.env.PORT || 5000;

connectDB().then(() => {
  app.listen(PORT, () => {
    console.log(`[server] BugScope AI backend listening on port ${PORT}`);
  });
});

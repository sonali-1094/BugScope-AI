require("dotenv").config();
const fs = require("node:fs/promises");
const path = require("node:path");
const { getPool, closeDB } = require("../config/db");

async function migrate() {
  const pool = getPool();
  await pool.query("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())");
  const files = (await fs.readdir(path.join(__dirname, "..", "migrations")))
    .filter((name) => /^\d+_.+\.sql$/.test(name)).sort();
  for (const name of files) {
    const { rowCount } = await pool.query("SELECT 1 FROM schema_migrations WHERE name = $1", [name]);
    if (rowCount) continue;
    const sql = await fs.readFile(path.join(__dirname, "..", "migrations", name), "utf8");
    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      await client.query(sql);
      await client.query("INSERT INTO schema_migrations(name) VALUES ($1)", [name]);
      await client.query("COMMIT");
      console.log(`[migrate] applied ${name}`);
    } catch (error) {
      await client.query("ROLLBACK");
      console.error(`[migrate] failed ${name} (${error.code || error.name})`);
      throw error;
    } finally {
      client.release();
    }
  }
}

migrate().catch(() => { process.exitCode = 1; }).finally(closeDB);

const { Pool } = require("pg");

let pool;

function getPool() {
  if (!pool) {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL is not set. Add the Neon PostgreSQL URL to the project root .env file.");
    }

    pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      ssl: { rejectUnauthorized: true },
      max: Number(process.env.PG_POOL_MAX || 10),
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
    });
    pool.on("error", (error) => {
      console.error(`[db] PostgreSQL idle client error (${error.code || error.name})`);
    });
  }
  return pool;
}

async function connectDB() {
  const client = await getPool().connect();
  try {
    await client.query("SELECT 1");
  } catch (error) {
    client.release();
    throw new Error(`PostgreSQL connection failed (${error.code || error.name}). Check DATABASE_URL, network access, and Neon availability.`);
  }
  client.release();
  console.log("[db] connected to PostgreSQL");
}

async function closeDB() {
  if (pool) {
    const closingPool = pool;
    pool = undefined;
    await closingPool.end();
  }
}

module.exports = { getPool, connectDB, closeDB };

require("dotenv").config();

const { getPool, closeDB } = require("./config/db");

async function main() {
  try {
    const { rows } = await getPool().query(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    );
    console.log(`[db-check] connected; ${rows.length} public tables found`);
    for (const row of rows) console.log(row.table_name);
  } catch (error) {
    console.error(`[db-check] failed (${error.code || error.name})`);
    process.exitCode = 1;
  } finally {
    await closeDB();
  }
}

main();

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const serverPath = require.resolve("../server");

test("server loads the PostgreSQL backend without requiring the legacy Mongo connection", () => {
  const script = `
    const Module = require('node:module');
    const originalLoad = Module._load;
    const calls = [];
    Module._load = function(request, parent, isMain) {
      if (request === 'dotenv') {
        return { config() {} };
      }
      if (request === 'mongoose') {
        throw new Error('LEGACY_MONGOOSE_SHOULD_NOT_LOAD');
      }
      if (request === 'express') {
        calls.push(['load', request]);
        throw new Error('STOP_AFTER_ORDER_CHECK');
      }
      return originalLoad.call(this, request, parent, isMain);
    };
    try { require(${JSON.stringify(serverPath)}); }
    catch (error) {
      if (error.message !== 'STOP_AFTER_ORDER_CHECK') throw error;
    }
    process.stdout.write(JSON.stringify(calls));
  `;

  const result = spawnSync(process.execPath, ["-e", script], {
    encoding: "utf8",
    env: { ...process.env },
  });

  assert.equal(result.status, 0, result.stderr);
  const calls = JSON.parse(result.stdout);
  assert.deepEqual(calls[0], ["load", "express"]);
});

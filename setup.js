#!/usr/bin/env node
/**
 * AMT Chat — Node/Electron setup script.
 * Usage: node setup.js
 *
 * Checks Node.js version, runs npm install.
 */
const { execSync } = require("child_process");
const path = require("path");

function main() {
  const nodeVer = process.versions.node;
  const major = parseInt(nodeVer.split(".")[0], 10);
  console.log(`Node.js ${nodeVer}`);
  if (major < 18) {
    console.error("ERROR: Node.js 18+ required. Install from https://nodejs.org");
    process.exit(1);
  }

  console.log("Running npm install …");
  execSync("npm install", { cwd: path.resolve(__dirname), stdio: "inherit" });

  console.log("✓ Node setup complete");
  console.log("  next: npm run build:py   (PyInstaller → dist/amt-backend/)");
  console.log("  then: npm run build:win  (electron-builder → release/ NSIS)");
}

main();

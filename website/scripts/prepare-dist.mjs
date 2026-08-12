import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const root = process.cwd();
const exported = resolve(root, "out");
const dist = resolve(root, "dist");
const worker = resolve(root, "hosting", "server", "index.js");
const hostingConfig = resolve(root, ".openai", "hosting.json");

if (!existsSync(exported)) {
  throw new Error(`Static export not found: ${exported}`);
}

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
cpSync(exported, resolve(dist, "client"), { recursive: true });
mkdirSync(resolve(dist, "server"), { recursive: true });
mkdirSync(resolve(dist, ".openai"), { recursive: true });
cpSync(worker, resolve(dist, "server", "index.js"));
cpSync(hostingConfig, resolve(dist, ".openai", "hosting.json"));

console.log(`Prepared static site: ${dist}`);

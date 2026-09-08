// Matches sitegen/vault.py. Plaintext and CryptoKeys live only in this page's memory.
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });
const assetPattern = /^[a-f0-9]{32}\.bin$/;

function fromBase64(text) {
  return Uint8Array.from(atob(text), character => character.charCodeAt(0));
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

export class ContentVault {
  constructor(manifestUrl) {
    this.manifestUrl = new URL(manifestUrl, location.href);
    this.cache = new Map();
    this.lock();
  }

  lock() {
    this.key = null;
    this.catalog = null;
    this.manifest = null;
    this.cache.clear();
    this.generation = (this.generation || 0) + 1;
  }

  async open(passkey) {
    this.lock();
    if (!crypto.subtle) throw new Error("Open the site over HTTPS or localhost to unlock its content.");
    const generation = this.generation;
    const response = await fetch(this.manifestUrl, { cache: "no-cache" });
    if (!response.ok) throw new Error("The session archive could not be loaded. Please try again.");
    const manifest = await response.json();
    if (manifest.version !== 1 || manifest.cipher !== "AES-256-GCM" || manifest.kdf !== "PBKDF2-SHA256" ||
        !Number.isInteger(manifest.iterations) || manifest.iterations < 600000 || manifest.iterations > 2000000 ||
        !manifest.assets || !assetPattern.test(manifest.catalog)) {
      throw new Error("This session archive has an unsupported format.");
    }
    const salt = fromBase64(manifest.salt);
    if (salt.length !== 16) throw new Error("The session archive is damaged.");
    const material = await crypto.subtle.importKey("raw", encoder.encode(passkey), "PBKDF2", false, ["deriveKey"]);
    const key = await crypto.subtle.deriveKey(
      { name: "PBKDF2", salt, iterations: manifest.iterations, hash: "SHA-256" },
      material, { name: "AES-GCM", length: 256 }, false, ["decrypt"]
    );
    if (generation !== this.generation) throw new Error("The archive was locked.");
    this.manifest = manifest;
    this.key = key;
    try {
      this.catalog = JSON.parse(decoder.decode(await this.resource(manifest.catalog)));
      if (this.catalog.version !== 1) throw new Error("Unsupported catalog version.");
      const graph = this.catalog.graph;
      const knowledge = JSON.parse(decoder.decode(await this.resource(graph.asset, graph.sha256)));
      if (knowledge.schema_version !== 1) throw new Error("Unsupported knowledge version.");
      return knowledge;
    } catch (error) {
      this.lock();
      if (error.name === "OperationError") throw new Error("That passkey did not unlock the archive. Check it and try again.");
      throw error;
    }
  }

  async resource(name, expectedHash) {
    if (!this.key || !assetPattern.test(name) || !Object.hasOwn(this.manifest.assets, name)) {
      throw new Error("The archive is locked or this passage is unavailable.");
    }
    if (!this.cache.has(name)) {
      const key = this.key;
      const generation = this.generation;
      const cipherHash = this.manifest.assets[name];
      const pending = (async () => {
        const response = await fetch(new URL(name, this.manifestUrl));
        if (!response.ok) throw new Error("A passage could not be loaded. Please try again.");
        const raw = new Uint8Array(await response.arrayBuffer());
        if (raw.length < 28 || await sha256(raw) !== cipherHash) throw new Error("The session archive changed or is damaged. Refresh and try again.");
        const bytes = await crypto.subtle.decrypt(
          { name: "AES-GCM", iv: raw.slice(0, 12), additionalData: encoder.encode(`structured-anarchy:v1:${name}`), tagLength: 128 },
          key, raw.slice(12)
        );
        if (generation !== this.generation) throw new Error("The archive was locked.");
        return bytes;
      })();
      this.cache.set(name, pending);
      pending.catch(() => { if (this.cache.get(name) === pending) this.cache.delete(name); });
    }
    const raw = await this.cache.get(name);
    if (expectedHash && await sha256(raw) !== expectedHash) throw new Error("A passage failed its content check.");
    return raw;
  }

  async source(fileName) {
    const entry = this.catalog?.files.find(file => file.file_name === fileName);
    if (!entry) throw new Error("The cited transcript is absent from this archive.");
    return decoder.decode(await this.resource(entry.asset, entry.sha256));
  }
}

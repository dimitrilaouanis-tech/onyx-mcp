/**
 * oa1.js — JavaScript reference implementation of the Onyx Attestation protocol
 * (OA-1). The Node sibling of oa1.py, byte-for-byte interoperable: an envelope
 * signed by oa1.py verifies here, and one signed here verifies in oa1.py or the
 * Onyx production signer. Zero dependencies — Node's built-in crypto only.
 *
 *   const { sign, verify, claimId, bindOutcome, generateKey } = require('./oa1');
 *   const out = sign({ verdict: 'BLOCK', risk_score: 100 }, { tool: 'my_tool' });
 *   verify(out);     // { ok: true, kid: '...' }
 *   claimId(out);    // 'sha256:...'  content-addressed id
 *
 * The reserved protocol field is `onyx_attestation`; the issuer is identified by
 * its kid / public_key, not the field name. Bring your own key and you are a
 * first-class OA-1 issuer.
 *
 * Spec:    https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1
 * License: MIT (this file) / CC0 (the spec text).
 */
'use strict';
const crypto = require('crypto');

const ATTESTATION_FIELD = 'onyx_attestation';
const ALG = 'Ed25519+JCS';
const SPEC = 'https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1';

// DER prefixes that wrap a raw 32-byte Ed25519 key so Node can import it.
const SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');     // public
const PKCS8_PREFIX = Buffer.from('302e020100300506032b657004220420', 'hex'); // private

function _b64u(buf) { return Buffer.from(buf).toString('base64url'); }
function _b64uDecode(s) { return Buffer.from(String(s), 'base64url'); }

/** RFC 8785 JCS: recursive key sort, compact separators, literal UTF-8 —
 *  byte-identical to Python json.dumps(sort_keys, ",",":", ensure_ascii=False). */
function jcs(o) {
  if (o === null || typeof o !== 'object') return JSON.stringify(o);
  if (Array.isArray(o)) return '[' + o.map(jcs).join(',') + ']';
  return '{' + Object.keys(o).sort().map(k => JSON.stringify(k) + ':' + jcs(o[k])).join(',') + '}';
}

function _canonical(payload) {
  const body = Object.assign({}, payload);
  delete body[ATTESTATION_FIELD];
  return Buffer.from(jcs(body), 'utf8');
}

function _pubKeyObj(raw32) {
  return crypto.createPublicKey({ key: Buffer.concat([SPKI_PREFIX, raw32]), format: 'der', type: 'spki' });
}
function _privKeyObj(raw32) {
  return crypto.createPrivateKey({ key: Buffer.concat([PKCS8_PREFIX, raw32]), format: 'der', type: 'pkcs8' });
}
function _rawPub(privObj) {
  // derive the public key from the private key, then take the raw 32 bytes
  return crypto.createPublicKey(privObj).export({ type: 'spki', format: 'der' }).subarray(-32);
}

/** Mint a fresh keypair; returns the base64 (std) private key to store as a secret. */
function generateKey() {
  const { privateKey } = crypto.generateKeyPairSync('ed25519');
  return privateKey.export({ type: 'pkcs8', format: 'der' }).subarray(-32).toString('base64');
}

function loadKey(b64) {
  const raw = b64 || process.env.OA1_PRIVATE_KEY || process.env.ONYX_AR1_PRIVATE_KEY;
  if (raw) {
    try { return _privKeyObj(Buffer.from(raw, 'base64').subarray(-32)); } catch (_) {}
  }
  return crypto.generateKeyPairSync('ed25519').privateKey;
}

/** Seal `payload` with an OA-1 attestation. Mutates and returns it. */
function sign(payload, opts = {}) {
  if (payload === null || typeof payload !== 'object') return payload;
  const priv = opts.keyObj || loadKey(opts.key);
  const rawPub = _rawPub(priv);
  const canonical = _canonical(payload);
  const issuer = opts.issuer || 'onyx';
  const base = (opts.publicUrl || 'https://onyx-actions.onrender.com').replace(/\/+$/, '');
  const kid = issuer + '-' + crypto.createHash('sha256').update(rawPub).digest('hex').slice(0, 16);
  payload[ATTESTATION_FIELD] = {
    alg: ALG,
    kid,
    public_key: _b64u(rawPub),
    tool: opts.tool || payload.tool || '',
    observed_hash: 'sha256:' + crypto.createHash('sha256').update(canonical).digest('hex'),
    signed_at: Math.floor(Date.now() / 1000),
    spec: SPEC,
    verify_pubkey_at: base + '/.well-known/onyx-pubkey',
    sig: _b64u(crypto.sign(null, canonical, priv)),
  };
  return payload;
}

/** Verify an OA-1 envelope offline using the embedded public key. */
function verify(payload) {
  const att = (payload || {})[ATTESTATION_FIELD];
  if (!att || typeof att !== 'object') return { ok: false, reason: 'no_attestation' };
  if (!att.sig || String(att.sig).startsWith('unsigned:')) return { ok: false, reason: 'unsigned' };
  try {
    const canonical = _canonical(payload);
    if (att.observed_hash !== 'sha256:' + crypto.createHash('sha256').update(canonical).digest('hex')) {
      return { ok: false, reason: 'hash_mismatch', kid: att.kid };
    }
    const ok = crypto.verify(null, canonical, _pubKeyObj(_b64uDecode(att.public_key)), _b64uDecode(att.sig));
    return ok ? { ok: true, kid: att.kid, alg: att.alg } : { ok: false, reason: 'sig_verify_failed' };
  } catch (e) {
    return { ok: false, reason: 'sig_verify_failed', detail: String(e).slice(0, 200) };
  }
}

function claimId(payload) {
  return ((payload || {})[ATTESTATION_FIELD] || {}).observed_hash || null;
}

/** Part 2 of OA-1: bind a real-world outcome to a signed claim — accepted only
 *  if the claim's signature verifies first. */
function bindOutcome(signedClaim, outcome, opts = {}) {
  const v = verify(signedClaim);
  if (!v.ok) return { ok: false, error: 'unverifiable_claim', reason: v.reason };
  const att = signedClaim[ATTESTATION_FIELD] || {};
  return {
    ok: true,
    claim_id: att.observed_hash,
    issuer_kid: att.kid,
    tool: att.tool,
    verdict: signedClaim.verdict || signedClaim.status,
    outcome,
    tx_hash: opts.txHash || null,
    detail: opts.detail || null,
    bound_at: Math.floor(Date.now() / 1000),
  };
}

module.exports = { sign, verify, claimId, bindOutcome, generateKey, loadKey, jcs, ATTESTATION_FIELD };

if (require.main === module) {
  const fs = require('fs');
  if (process.argv[2]) {
    console.log(JSON.stringify(verify(JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))), null, 2));
  } else {
    const out = sign({ verdict: 'BLOCK', risk_score: 100 }, { tool: 'demo' });
    console.log('self  verify:', verify(out));
    out.risk_score = 0;
    console.log('tamper test :', verify(out));
  }
}

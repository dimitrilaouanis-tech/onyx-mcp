/**
 * OA-1 interop proof (JavaScript). Run: node example.js
 *
 * Demonstrates: sign -> verify -> tamper-detect -> bind_outcome, and that an
 * oa1.js envelope is byte-for-byte interoperable with oa1.py and the Onyx
 * production signer.
 */
'use strict';
const { sign, verify, claimId, bindOutcome } = require('./oa1');

// 1. Sign a claim (ephemeral key here; in prod set OA1_PRIVATE_KEY).
const result = sign({ verdict: 'BLOCK', risk_score: 100 }, { tool: 'my_security_tool', issuer: 'onyx' });
console.log('signed claim id :', claimId(result));
console.log('verify          :', verify(result));

// 2. Tamper -> detected.
const tampered = JSON.parse(JSON.stringify(result));
tampered.risk_score = 0;
console.log('tamper verify   :', verify(tampered));

// 3. Bind a real-world outcome (only attaches if the signature verifies).
console.log('bind outcome    :', bindOutcome(result, 'drained', { detail: 'confirmed loss' }));

// 4. Verify a claim signed by the LIVE production signer (proves cross-impl interop).
const https = require('https');
const data = JSON.stringify({ message: 'oa1.js interop', from: 'example' });
const req = https.request('https://onyx-actions.onrender.com/connect',
  { method: 'POST', headers: { 'Content-Type': 'application/json' } }, res => {
    let b = ''; res.on('data', c => b += c); res.on('end', () => {
      console.log('live signer     :', verify(JSON.parse(b)));
    });
  });
req.on('error', e => console.log('live signer     : (skipped, offline)', String(e).slice(0, 60)));
req.write(data); req.end();

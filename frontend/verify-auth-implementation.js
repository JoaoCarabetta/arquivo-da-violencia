#!/usr/bin/env node

/**
 * Verification script for authentication error handling implementation
 * This script checks that the code contains the expected patterns
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const checks = [];
let allPassed = true;

function checkFile(filePath, patterns, description) {
  const fullPath = path.join(__dirname, filePath);
  
  if (!fs.existsSync(fullPath)) {
    console.error(`❌ File not found: ${filePath}`);
    allPassed = false;
    return;
  }
  
  const content = fs.readFileSync(fullPath, 'utf-8');
  const missing = [];
  
  patterns.forEach(pattern => {
    if (!content.includes(pattern)) {
      missing.push(pattern);
    }
  });
  
  if (missing.length === 0) {
    console.log(`✅ ${description}`);
    checks.push({ file: filePath, status: 'PASS', description });
  } else {
    console.error(`❌ ${description}`);
    console.error(`   Missing patterns: ${missing.join(', ')}`);
    checks.push({ file: filePath, status: 'FAIL', description, missing });
    allPassed = false;
  }
}

console.log('🔍 Verifying Authentication Error Handling Implementation\n');

// Check api.ts
checkFile(
  'src/lib/api.ts',
  [
    'response.status === 401',
    'localStorage.removeItem(\'admin_token\')',
    'new CustomEvent(\'auth-token-cleared\')',
    'window.location.pathname.startsWith(\'/admin\')',
    'window.location.href = \'/admin/login\'',
    'Authentication failed. Please log in again.'
  ],
  'api.ts: 401 error handling with token clearing and redirect'
);

// Check AuthContext.tsx
checkFile(
  'src/contexts/AuthContext.tsx',
  [
    'addEventListener(\'storage\'',
    'addEventListener(\'auth-token-cleared\'',
    'removeEventListener(\'storage\'',
    'removeEventListener(\'auth-token-cleared\''
  ],
  'AuthContext.tsx: Event listeners for storage and custom events'
);

// Check Dashboard.tsx
checkFile(
  'src/pages/admin/Dashboard.tsx',
  [
    'isAuthError',
    'Authentication failed. Please log in again.',
    'Go to login',
    '/admin/login'
  ],
  'Dashboard.tsx: Auth error detection and user-friendly messages'
);

console.log('\n' + '='.repeat(60));
if (allPassed) {
  console.log('✅ All checks passed! Implementation looks correct.');
  process.exit(0);
} else {
  console.log('❌ Some checks failed. Please review the implementation.');
  process.exit(1);
}


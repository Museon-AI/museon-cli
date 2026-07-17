'use strict';

const fs = require('node:fs');
const path = require('node:path');
const process = require('node:process');
const { spawn } = require('node:child_process');

const PLATFORM_PACKAGES = Object.freeze({
  'darwin-arm64': Object.freeze({
    packageName: '@museon/cli-darwin-arm64',
    binary: 'bin/museoncli/museoncli',
  }),
  'darwin-x64': Object.freeze({
    packageName: '@museon/cli-darwin-x64',
    binary: 'bin/museoncli/museoncli',
  }),
  'linux-arm64-gnu': Object.freeze({
    packageName: '@museon/cli-linux-arm64-gnu',
    binary: 'bin/museoncli/museoncli',
  }),
  'linux-x64-gnu': Object.freeze({
    packageName: '@museon/cli-linux-x64-gnu',
    binary: 'bin/museoncli/museoncli',
  }),
  'win32-x64': Object.freeze({
    packageName: '@museon/cli-win32-x64',
    binary: 'bin/museoncli/museoncli.exe',
  }),
  'win32-arm64': Object.freeze({
    packageName: '@museon/cli-win32-arm64',
    binary: 'bin/museoncli/museoncli.exe',
  }),
});

class DistributionError extends Error {
  constructor(message) {
    super(message);
    this.name = 'MuseonDistributionError';
  }
}

function linuxLibc(report = undefined) {
  let value = report;
  if (value === undefined && process.report && typeof process.report.getReport === 'function') {
    value = process.report.getReport();
  }
  const header = value && typeof value === 'object' ? value.header : undefined;
  return header && header.glibcVersionRuntime ? 'gnu' : 'musl';
}

function selectPlatform(options = {}) {
  const platform = options.platform || process.platform;
  const arch = options.arch || process.arch;
  let target = `${platform}-${arch}`;
  if (platform === 'linux') {
    const libc = linuxLibc(options.report);
    if (libc !== 'gnu') {
      throw new DistributionError(
        'Museon CLI provides Linux native packages for glibc only; this host appears to use musl. ' +
        'Use the immutable GitHub/uv fallback documented at https://www.museon.ai/cli/install.md.'
      );
    }
    target += '-gnu';
  }
  const selection = PLATFORM_PACKAGES[target];
  if (!selection) {
    throw new DistributionError(
      `Museon CLI does not provide a native package for ${platform}/${arch}. ` +
      'Supported targets are macOS arm64/x64, Linux glibc arm64/x64, and Windows arm64/x64.'
    );
  }
  return selection;
}

function readRootManifest() {
  return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
}

function resolveNativeBinary(selection, expectedVersion, options = {}) {
  const resolve = options.resolve || require.resolve;
  const readFile = options.readFile || ((file) => fs.readFileSync(file, 'utf8'));
  const fileExists = options.exists || fs.existsSync;
  let manifestPath;
  try {
    manifestPath = resolve(`${selection.packageName}/package.json`);
  } catch (error) {
    throw new DistributionError(
      `The optional native package ${selection.packageName}@${expectedVersion} is missing. ` +
      `Reinstall with \`npm install --global @museon/cli@${expectedVersion} --include=optional\` ` +
      'and ensure your npm configuration does not omit optional dependencies.'
    );
  }
  const manifest = JSON.parse(readFile(manifestPath));
  if (manifest.version !== expectedVersion) {
    throw new DistributionError(
      `Version mismatch: @museon/cli is ${expectedVersion}, but ${selection.packageName} is ` +
      `${manifest.version || 'unknown'}. Reinstall the exact root package version.`
    );
  }
  const binary = path.join(path.dirname(manifestPath), ...selection.binary.split('/'));
  if (!fileExists(binary)) {
    throw new DistributionError(
      `The native executable is missing from ${selection.packageName}@${expectedVersion}. ` +
      'Clear the npm cache and reinstall; npm install scripts are not required.'
    );
  }
  return binary;
}

function childEnvironment(environment = process.env) {
  return { ...environment, MUSEONCLI_DISTRIBUTION_CHANNEL: 'npm' };
}

function runNative(argv, options = {}) {
  const manifest = options.manifest || readRootManifest();
  const selection = options.selection || selectPlatform(options.platformOptions);
  const binary = options.binary || resolveNativeBinary(selection, manifest.version, options.resolver);
  const spawnChild = options.spawn || spawn;
  const hostProcess = options.process || process;
  const child = spawnChild(binary, argv, {
    stdio: 'inherit',
    env: childEnvironment(hostProcess.env),
    windowsHide: false,
  });
  child.on('error', (error) => {
    hostProcess.stderr.write(`Museon CLI could not start: ${error.message}\n`);
    hostProcess.exitCode = 1;
  });
  child.on('exit', (code, signal) => {
    if (signal) {
      try {
        hostProcess.kill(hostProcess.pid, signal);
      } catch (_error) {
        hostProcess.exitCode = 1;
      }
      return;
    }
    hostProcess.exitCode = code === null ? 1 : code;
  });
  return child;
}

function main() {
  try {
    runNative(process.argv.slice(2));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`Museon CLI installation error: ${message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  DistributionError,
  PLATFORM_PACKAGES,
  childEnvironment,
  linuxLibc,
  main,
  resolveNativeBinary,
  runNative,
  selectPlatform,
};

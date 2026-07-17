'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const path = require('node:path');
const test = require('node:test');

const launcher = require('../templates/root/lib/launcher.cjs');

const cases = [
  ['darwin', 'arm64', undefined, '@museon/cli-darwin-arm64'],
  ['darwin', 'x64', undefined, '@museon/cli-darwin-x64'],
  ['linux', 'arm64', { header: { glibcVersionRuntime: '2.35' } }, '@museon/cli-linux-arm64-gnu'],
  ['linux', 'x64', { header: { glibcVersionRuntime: '2.35' } }, '@museon/cli-linux-x64-gnu'],
  ['win32', 'x64', undefined, '@museon/cli-win32-x64'],
  ['win32', 'arm64', undefined, '@museon/cli-win32-arm64'],
];

for (const [platform, arch, report, expected] of cases) {
  test(`selects ${expected}`, () => {
    assert.equal(launcher.selectPlatform({ platform, arch, report }).packageName, expected);
  });
}

test('rejects musl with an actionable fallback', () => {
  assert.throws(
    () => launcher.selectPlatform({ platform: 'linux', arch: 'x64', report: { header: {} } }),
    /glibc only.*GitHub\/uv/s
  );
});

test('rejects unsupported targets', () => {
  assert.throws(
    () => launcher.selectPlatform({ platform: 'freebsd', arch: 'x64' }),
    /does not provide.*freebsd\/x64/s
  );
});

test('reports an omitted optional dependency', () => {
  const selection = launcher.PLATFORM_PACKAGES['darwin-arm64'];
  assert.throws(
    () => launcher.resolveNativeBinary(selection, '1.2.3', { resolve: () => { throw new Error('missing'); } }),
    /cli-darwin-arm64@1\.2\.3.*--include=optional/s
  );
});

test('rejects a platform package with a different version', () => {
  const selection = launcher.PLATFORM_PACKAGES['darwin-arm64'];
  assert.throws(
    () => launcher.resolveNativeBinary(selection, '1.2.3', {
      resolve: () => path.join('/tmp', 'package.json'),
      readFile: () => JSON.stringify({ version: '1.2.2' }),
      exists: () => true,
    }),
    /Version mismatch.*1\.2\.2/s
  );
});

test('inherits args and stdio, changes only the distribution-channel env, and preserves exit code', () => {
  const events = new EventEmitter();
  const calls = [];
  const fakeProcess = {
    env: { KEEP: 'yes' },
    stderr: { write() {} },
    pid: 123,
    kill() {},
    exitCode: undefined,
  };
  launcher.runNative(['schema', '--json'], {
    manifest: { version: '1.2.3' },
    selection: launcher.PLATFORM_PACKAGES['darwin-arm64'],
    binary: '/native/museoncli',
    process: fakeProcess,
    spawn(binary, args, options) {
      calls.push({ binary, args, options });
      return events;
    },
  });
  assert.deepEqual(calls, [{
    binary: '/native/museoncli',
    args: ['schema', '--json'],
    options: {
      stdio: 'inherit',
      env: { KEEP: 'yes', MUSEONCLI_DISTRIBUTION_CHANNEL: 'npm' },
      windowsHide: false,
    },
  }]);
  events.emit('exit', 7, null);
  assert.equal(fakeProcess.exitCode, 7);
});

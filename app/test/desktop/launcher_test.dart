import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/desktop/browser.dart';
import 'package:leetcode_guard/desktop/launcher.dart';
import 'package:leetcode_guard/desktop/open_route.dart';
import 'package:leetcode_guard/desktop/sources.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';

class _FakeProcess implements Process {
  @override
  Future<int> get exitCode async => 0;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  late Directory tmp;

  setUp(() => tmp = Directory.systemTemp.createTempSync('lg-launch'));
  tearDown(() => tmp.deleteSync(recursive: true));

  test('fixtureArg finds --fixture <file>', () {
    expect(fixtureArg(['--fixture', 'a.json']), 'a.json');
    expect(fixtureArg(['--serve-only']), isNull);
    expect(fixtureArg(['--fixture']), isNull);
  });

  test('a fixture source re-reads the file on every fetch', () async {
    final file = File('${tmp.path}/f.json')..writeAsStringSync('1');
    final source = FileSnapshotSource(file);
    expect(await source.fetch(), '1');
    file.writeAsStringSync('2');
    expect(await source.fetch(), '2');
    file.deleteSync();
    expect(await source.fetch(), isNull);
    // No heartbeat in fixture mode: the app falls back to generated_at.
    expect(await source.heartbeat(), isNull);
  });

  test('the live source is the exporter file under ~/.local/share', () {
    expect(
      localSnapshotFile('/home/k').path,
      '/home/k/.local/share/leetcode_guard/snapshot.json',
    );
  });

  test('the local source reads the file and beats with its mtime', () async {
    final file = File('${tmp.path}/snapshot.json');
    final source = LocalSnapshotSource(file);
    // Not exported yet: nothing published, no heartbeat.
    expect(await source.fetch(), isNull);
    expect(await source.heartbeat(), isNull);
    file.writeAsStringSync('{"schema": 1}');
    final written = DateTime.utc(2026, 10, 23, 12, 5, 7);
    file.setLastModifiedSync(written);
    expect(await source.fetch(), '{"schema": 1}');
    final beat = await source.heartbeat();
    expect(parseHeartbeat(beat), written);
    expect(jsonDecode(beat!), isA<String>());
  });

  test('an unreadable local file is unavailable, naming it', () async {
    final dir = Directory('${tmp.path}/snapshot.json')..createSync();
    final source = LocalSnapshotSource(File(dir.path));
    await expectLater(
      source.fetch(),
      throwsA(
        isA<SnapshotUnavailable>().having(
          (e) => e.message,
          'message',
          contains('snapshot.json'),
        ),
      ),
    );
  });

  test('resolveWebRoot prefers the bundled web dir', () {
    final exe = Directory('${tmp.path}/bundle/bin')
      ..createSync(recursive: true);
    expect(resolveWebRoot(exeDir: exe.path, cwd: '/src'), '/src/build/web');
    Directory('${tmp.path}/bundle/web').createSync();
    expect(
      resolveWebRoot(exeDir: exe.path, cwd: '/src'),
      '${tmp.path}/bundle/web',
    );
  });

  test('findBrowser honours the override and skips missing paths', () {
    expect(findBrowser(override: '/x', exists: (p) => p == '/x'), '/x');
    expect(
      findBrowser(override: '', exists: (p) => p == '/usr/bin/chromium'),
      '/usr/bin/chromium',
    );
    expect(findBrowser(override: '', exists: (_) => false), '');
    expect(findBrowser(exists: (_) => false), '');
  });

  test('the window resolves loopback only and uses no proxy', () {
    final args = browserArgs('/home/k');
    // One argv element, no shell quotes: Process.start passes it verbatim.
    // `localhost` must be excluded by name: `MAP *` matches it before the
    // 127.0.0.1 exclusion is consulted, and the app's origin is localhost.
    expect(
      args,
      contains(
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, '
        'EXCLUDE 127.0.0.1',
      ),
    );
    expect(args, contains('--no-proxy-server'));
    // Chrome flags the resolver rules as "unsupported" with an infobar
    // across the top of the window on every launch; --test-type hides it.
    expect(args, contains('--test-type'));
    expect(args.where((a) => a.contains('"') || a.contains("'")), isEmpty);
  });

  test('browserArgs pin the profile, origin and WM_CLASS', () {
    final args = browserArgs('/home/k');
    expect(args, contains('--app=http://localhost:$kWrapperPort'));
    expect(
      args,
      contains(
        '--user-data-dir=/home/k/.local/share/leetcode-guard-app/profile',
      ),
    );
    expect(args, contains('--class=leetcode-guard-app'));
  });

  test('the window loads no extension and opens nothing but itself', () {
    final args = browserArgs('/home/k');
    // The flags wrapper injects --load-extension (a claude.ai login tab);
    // --disable-extensions must therefore ride along with every launch.
    expect(args, contains('--disable-extensions'));
    expect(args.where((a) => a.startsWith('--load-extension')), isEmpty);
    expect(args, contains('--no-first-run'));
    expect(args, contains('--no-default-browser-check'));
    expect(args, contains('--disable-session-crashed-bubble'));
    expect(args, contains('--hide-crash-restore-bubble'));
    expect(
      args.where((a) => a.startsWith('--disable-features=')),
      hasLength(1),
    );
  });

  test('the real binary is tried before the flags-injecting wrapper', () {
    const real = '/usr/lib/chromium/chromium';
    expect(
      findBrowser(
        override: '',
        exists: (p) => p == real || p == '/usr/bin/chromium',
      ),
      real,
    );
  });

  Future<List<String>> run(
    List<String> args, {
    String browser = '/b',
    bool busy = false,
    List<String>? opened,
  }) async {
    final log = <String>[];
    final err = StringBuffer();
    await runDesktop(
      args,
      home: tmp.path,
      exeDir: tmp.path,
      cwd: tmp.path,
      startServer: (root, source) async {
        log.add('serve ${source.runtimeType}');
        if (busy) throw const SocketException('in use');
      },
      browserFinder: () => browser,
      scaleFinder: () async => 2,
      startProcess: (exe, a) async {
        opened?.addAll(a);
        log.add('open $exe');
        return _FakeProcess();
      },
      hold: () async => log.add('hold'),
      err: err.writeln,
    );
    return [...log, if (err.isNotEmpty) err.toString().trim()];
  }

  test('runDesktop serves, opens the window and holds', () async {
    expect(await run([]), ['serve LocalSnapshotSource', 'open /b', 'hold']);
  });

  test('--fixture serves the file instead of Firebase', () async {
    expect(
      (await run(['--fixture', 'f.json', '--serve-only'])).single,
      'serve FileSnapshotSource',
    );
  });

  test('an already running wrapper just opens another window', () async {
    final log = await run([], busy: true);
    expect(log, contains('open /b'));
    // Not ours to keep alive: the running wrapper does the serving.
    expect(log, isNot(contains('hold')));
    expect(log.last, contains('already running'));
  });

  test('--window-only opens a window onto the running wrapper', () async {
    expect(await run(['--window-only']), ['open /b']);
  });

  test('the window opens at the detected device scale', () async {
    final opened = <String>[];
    await run(['--window-only'], opened: opened);
    expect(opened, contains('--force-device-scale-factor=2'));
  });

  test('xdgOpen hands the URL over detached, as one argument', () async {
    final calls = <String>[];
    await xdgOpen(
      'https://leetcode.com/problems/two-sum/',
      start: (exe, args, {mode = ProcessStartMode.normal}) async {
        calls.add('$exe ${args.length} ${args.join('|')} $mode');
        return _FakeProcess();
      },
    );
    const url = 'https://leetcode.com/problems/two-sum/';
    expect(calls, ['xdg-open 1 $url ${ProcessStartMode.detached}']);
  });

  test('no browser: says where to point one', () async {
    final log = await run([], browser: '');
    expect(log.last, contains('LEETCODE_GUARD_BROWSER'));
    expect(log, isNot(contains('hold')));
  });

  test('startWrapper binds a real server', () async {
    final server = await startWrapper(
      tmp.path,
      FileSnapshotSource(File('${tmp.path}/none.json')),
      port: 0,
    );
    await server.close();
  });
}

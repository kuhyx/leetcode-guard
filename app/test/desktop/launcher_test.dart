import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/desktop/browser.dart';
import 'package:leetcode_guard/desktop/launcher.dart';
import 'package:leetcode_guard/desktop/sources.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';

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

  test('the live source reads the shared crdt-sync credential', () async {
    final dir = Directory('${tmp.path}/.config/crdt-sync')
      ..createSync(recursive: true);
    File('${dir.path}/firebase.json').writeAsStringSync(
      '{"apiKey": "k", "databaseUrl": "https://db.example", '
      '"projectId": "p", "uid": "u", "email": "e@x"}',
    );
    File('${dir.path}/password').writeAsStringSync('pw\n');
    final asked = <String>[];
    final source = crdtSyncSource(
      tmp.path,
      httpClient: MockClient((r) async {
        asked.add(r.url.path);
        if (r.url.host == 'identitytoolkit.googleapis.com') {
          expect(r.body, contains('pw'));
          return http.Response(
            '{"idToken": "t", "refreshToken": "r", "expiresIn": "3600", '
            '"localId": "u"}',
            200,
          );
        }
        return http.Response('{"schema": 1}', 200);
      }),
    );
    expect(await source.fetch(), '{"schema": 1}');
    expect(asked.last, '/leetcode-guard/status.json');
    expect(await source.heartbeat(), '{"schema": 1}');
    expect(asked.last, '/leetcode-guard/heartbeat.json');
  });

  test('a missing credential is unavailable, naming the file', () async {
    final source = crdtSyncSource(tmp.path);
    await expectLater(
      source.fetch(),
      throwsA(
        isA<SnapshotUnavailable>().having(
          (e) => e.message,
          'message',
          contains('crdt-sync'),
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

  Future<List<String>> run(
    List<String> args, {
    String browser = '/b',
    bool busy = false,
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
      startProcess: (exe, a) async {
        log.add('open $exe');
        return _FakeProcess();
      },
      hold: () async => log.add('hold'),
      err: err.writeln,
    );
    return [...log, if (err.isNotEmpty) err.toString().trim()];
  }

  test('runDesktop serves, opens the window and holds', () async {
    expect(await run([]), ['serve LiveSnapshotSource', 'open /b', 'hold']);
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
    expect(log.last, contains('already running'));
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

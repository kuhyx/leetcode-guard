import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';

import '../support/fakes.dart';

void main() {
  late Directory root;
  late WrapperServer server;
  late int port;
  final client = HttpClient();

  Future<(int, String, String?)> get(String path) async {
    final request = await client.get('127.0.0.1', port, path);
    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();
    return (response.statusCode, body, response.headers.contentType?.mimeType);
  }

  Future<void> serve(List<Object?> answers) async {
    server = WrapperServer(webRoot: root.path, source: FakeSource(answers));
    port = await server.start(port: 0);
  }

  setUp(() {
    root = Directory.systemTemp.createTempSync('lg-web');
    File('${root.path}/index.html').writeAsStringSync('<html></html>');
    File('${root.path}/main.dart.wasm').writeAsStringSync('w');
  });

  tearDown(() async {
    await server.close();
    root.deleteSync(recursive: true);
  });

  test('serves the web build with real content types', () async {
    await serve([null]);
    expect(await get('/'), (200, '<html></html>', 'text/html'));
    expect((await get('/main.dart.wasm')).$3, 'application/wasm');
    expect((await get('/missing.js')).$1, 404);
  });

  test('refuses paths outside the web root', () async {
    await serve([null]);
    expect((await get('/..%2F..%2Fetc%2Fpasswd')).$1, 403);
  });

  test('/snapshot.json is the source body, never cached', () async {
    await serve(['{"schema": 1}']);
    final request = await client.get('127.0.0.1', port, '/snapshot.json');
    final response = await request.close();
    expect(response.statusCode, 200);
    expect(response.headers.value('cache-control'), 'no-store');
    expect(await response.transform(utf8.decoder).join(), '{"schema": 1}');
  });

  test('/heartbeat.json is the source heartbeat', () async {
    server = WrapperServer(
      webRoot: root.path,
      source: FakeSource(['{}'], heartbeats: ['"2026-10-23T14:05:00Z"', null]),
    );
    port = await server.start(port: 0);
    expect(await get('/heartbeat.json'), (
      200,
      '"2026-10-23T14:05:00Z"',
      'application/json',
    ));
    expect((await get('/heartbeat.json')).$1, 404);
  });

  test('nothing published is 404', () async {
    await serve([null]);
    expect((await get('/snapshot.json')).$1, 404);
  });

  test('an unavailable source is 502 with the reason', () async {
    await serve([const SnapshotUnavailable('offline')]);
    expect(await get('/snapshot.json'), (502, 'offline', 'text/plain'));
  });

  test('an unexpected failure is 500, and the server keeps serving', () async {
    await serve([const FormatException('bad'), '{"ok": 1}']);
    expect((await get('/snapshot.json')).$1, 500);
    expect((await get('/snapshot.json')).$2, '{"ok": 1}');
  });

  test('content types cover the web build', () {
    String type(String f) => WrapperServer.contentTypeFor(f).mimeType;
    expect(type('a.js'), 'text/javascript');
    expect(type('a.mjs'), 'text/javascript');
    expect(type('a.json'), 'application/json');
    expect(type('a.css'), 'text/css');
    expect(type('a.png'), 'image/png');
    expect(type('a.svg'), 'image/svg+xml');
    expect(type('a.ttf'), 'font/ttf');
    expect(type('a.otf'), 'font/otf');
    expect(type('a.woff2'), 'font/woff2');
    expect(type('a.bin'), 'application/octet-stream');
  });
}

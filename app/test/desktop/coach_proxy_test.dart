import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/desktop/coach_proxy.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';

import '../support/fakes.dart';

/// What the fake relay saw.
class _Seen {
  new(this.method, this.uri, this.host, this.type, this.body);

  final String method;
  final Uri uri;
  final String? host;
  final String? type;
  final String body;
}

void main() {
  late Directory root;
  late HttpServer relay;
  late WrapperServer wrapper;
  late int port;
  final seen = <_Seen>[];
  var answer = (202, '{"rid": "x"}');
  var hang = false;
  final client = HttpClient();

  setUp(() async {
    seen.clear();
    answer = (202, '{"rid": "x"}');
    hang = false;
    root = Directory.systemTemp.createTempSync('lg-web');
    relay = await HttpServer.bind(InternetAddress.loopbackIPv4, 0)
      ..listen((req) async {
        final body = await utf8.decoder.bind(req).join();
        seen.add(
          _Seen(
            req.method,
            req.uri,
            req.headers.value('host'),
            req.headers.contentType?.mimeType,
            body,
          ),
        );
        if (hang) return;
        req.response
          ..statusCode = answer.$1
          ..headers.contentType = ContentType.json
          ..write(answer.$2);
        await req.response.close();
      });
    wrapper = WrapperServer(
      webRoot: root.path,
      source: FakeSource([null]),
      relay: Uri.parse('http://127.0.0.1:${relay.port}'),
      relayTimeout: const Duration(milliseconds: 300),
    );
    port = await wrapper.start(port: 0);
  });

  tearDown(() async {
    await wrapper.close();
    await relay.close(force: true);
    root.deleteSync(recursive: true);
  });

  Future<(int, String, String?)> call(
    String method,
    String path, {
    String? body,
    String type = 'application/json',
    String? origin,
  }) async {
    final request = await client.open(method, '127.0.0.1', port, path);
    if (origin != null) request.headers.set('origin', origin);
    if (body != null) {
      request.headers.set(HttpHeaders.contentTypeHeader, type);
      request.write(body);
    }
    final response = await request.close();
    final text = await response.transform(utf8.decoder).join();
    return (response.statusCode, text, response.headers.contentType?.mimeType);
  }

  test('forwards method, path, query and body; answers verbatim', () async {
    answer = (200, '{"m0002": {"role": "coach"}}');
    expect(await call('GET', '/coach/chat?after=m0001'), (
      200,
      '{"m0002": {"role": "coach"}}',
      'application/json',
    ));
    answer = (202, '{"rid": "01J"}');
    final body = jsonEncode({'rid': '01J', 'kind': 'hint'});
    expect((await call('POST', '/coach/requests', body: body)).$1, 202);
    expect(seen.map((s) => s.method), ['GET', 'POST']);
    expect(seen[0].uri.toString(), '/coach/chat?after=m0001');
    expect(seen[1].body, body);
    expect(seen[1].type, 'application/json');
    // The relay refuses any Host but its own (DNS rebinding).
    expect(seen.map((s) => s.host).toSet(), {'127.0.0.1:${relay.port}'});
  });

  test("the relay's own refusals pass through", () async {
    answer = (415, '{"ok": false}');
    expect(
      (await call('POST', '/coach/requests', body: 'x', type: 'text/plain')).$1,
      415,
    );
    expect(seen.single.type, 'text/plain');
  });

  test('a body over 16 KiB is refused unread', () async {
    final big = jsonEncode({'pad': 'x' * kMaxCoachBody});
    expect((await call('POST', '/coach/requests', body: big)).$1, 413);
    expect(seen, isEmpty);
  });

  test('only its own origin, or none (a same-origin GET)', () async {
    answer = (200, '{}');
    expect((await call('GET', '/coach/state', origin: 'https://evil')).$1, 403);
    expect(
      (await call('GET', '/coach/state', origin: 'http://localhost:$port')).$1,
      200,
    );
    expect(
      (await call('GET', '/coach/state', origin: 'http://127.0.0.1:$port')).$1,
      200,
    );
    expect((await call('GET', '/coach/state')).$1, 200);
    expect(seen, hasLength(3));
  });

  test(
    'relay down: 502 relay_down, exactly as the contract words it',
    () async {
      await relay.close(force: true);
      expect(await call('GET', '/coach/heartbeat'), (
        502,
        '{"ok":false,"code":"relay_down","error":"coach service not running"}',
        'application/json',
      ));
    },
  );

  test('a relay that never answers times out as 504', () async {
    hang = true;
    expect((await call('GET', '/coach/state')).$1, 504);
  });

  test('nothing outside /coach/ is forwarded', () async {
    expect((await call('GET', '/coachx')).$1, 404);
    expect((await call('GET', '/coach')).$1, 404);
    expect(seen, isEmpty);
  });

  test('the relay port comes from LEETCODE_COACH_RELAY_PORT', () {
    expect(relayFromEnv(const {}), Uri.parse('http://127.0.0.1:8777'));
    expect(
      relayFromEnv(const {'LEETCODE_COACH_RELAY_PORT': '9123'}),
      Uri.parse('http://127.0.0.1:9123'),
    );
    expect(
      relayFromEnv(const {'LEETCODE_COACH_RELAY_PORT': 'nope'}),
      Uri.parse('http://127.0.0.1:8777'),
    );
    expect(
      relayFromEnv(const {'LEETCODE_COACH_RELAY_PORT': '70000'}),
      Uri.parse('http://127.0.0.1:8777'),
    );
  });

  test('the wrapper defaults to the relay on 8777', () {
    final w = WrapperServer(webRoot: root.path, source: FakeSource([null]));
    expect(w.relay, Uri.parse('http://127.0.0.1:8777'));
    expect(w.relayTimeout, kRelayTimeout);
  });
}

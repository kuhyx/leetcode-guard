import 'dart:async';
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';

import '../support/fakes.dart';

class _Dev implements DeviceIdStore {
  @override
  Future<String> deviceId() async => '0b7e3c1a-1111-4222-8333-444455556666';
}

InMemoryCredentialStore _signedIn() {
  final store = InMemoryCredentialStore();
  unawaited(
    store.save(
      FirebaseCredentials(
        idToken: 'tok',
        refreshToken: 'r',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      ),
    ),
  );
  return store;
}

void main() {
  late List<http.Request> sent;
  late AppErrorLog log;

  RtdbErrorReporter reporter(
    Future<http.Response> Function(http.Request) answer, {
    bool signedOut = false,
    InMemoryCredentialStore? store,
  }) => RtdbErrorReporter(
    log: log,
    devices: _Dev(),
    open: () async => signedOut
        ? null
        : FirebaseRestClient(
            databaseUrl: 'https://db.example',
            auth: FirebaseTokenProvider(
              apiKey: 'k',
              store: store ?? _signedIn(),
            ),
          ),
    databaseUrl: 'https://db.example/',
    httpClient: MockClient((r) async {
      sent.add(r);
      return await answer(r);
    }),
  );

  setUp(() {
    sent = [];
    log = AppErrorLog(
      slot: MemorySlot(),
      clock: () => DateTime.utc(2026, 10, 24, 11, 5),
    );
  });

  test('nothing recorded: reaching Firebase writes nothing', () async {
    final r = reporter((_) async => http.Response('', 204));
    expect(await r.reached(), isFalse);
    expect(sent, isEmpty);
  });

  test('a recorded error is PUT once, as a string leaf, silently', () async {
    final r = reporter((_) async => http.Response('', 204));
    await r.failed("Offline: can't reach Firebase");
    expect(await r.reached(), isTrue);
    final [put] = sent;
    expect(put.method, 'PUT');
    expect(
      put.url.path,
      '/leetcode-guard/app_errors/0b7e3c1a-1111-4222-8333-444455556666.json',
    );
    expect(put.url.queryParameters, {'print': 'silent', 'auth': 'tok'});
    final leaf = jsonDecode(put.body) as String;
    final body = jsonDecode(leaf) as Map<String, Object?>;
    expect((body['errors']! as List).single, containsPair('count', 1));
    // Sent: the next contact has nothing to say.
    expect(await r.reached(), isFalse);
    expect(sent, hasLength(1));
  });

  test(
    'a failed upload keeps the errors pending and records nothing',
    () async {
      await log.record('x');
      for (final answer in <Future<http.Response> Function(http.Request)>[
        (_) async => http.Response('denied', 401),
        (_) async => throw http.ClientException('offline'),
      ]) {
        final r = reporter(answer);
        expect(await r.reached(), isFalse);
        expect((await log.entries()).single.count, 1);
        expect(await log.pending('d'), isNotNull);
      }
      final signedOut = reporter(
        (_) async => http.Response('', 204),
        signedOut: true,
      );
      expect(await signedOut.reached(), isFalse);
      final noSession = reporter(
        (_) async => http.Response('', 204),
        store: InMemoryCredentialStore(),
      );
      expect(await noSession.reached(), isFalse);
      expect((await log.entries()).single.count, 1);
    },
  );

  test('two contacts at once upload once', () async {
    final gate = Completer<http.Response>();
    final r = reporter((_) => gate.future);
    await r.failed('x');
    final first = r.reached();
    expect(await r.reached(), isFalse);
    gate.complete(http.Response('', 200));
    expect(await first, isTrue);
    expect(sent, hasLength(1));
  });

  test('defaults to a real HTTP client', () {
    final r = RtdbErrorReporter(
      log: log,
      devices: _Dev(),
      open: () async => null,
      databaseUrl: 'https://db.example',
    );
    expect(r.databaseUrl, 'https://db.example');
  });
}

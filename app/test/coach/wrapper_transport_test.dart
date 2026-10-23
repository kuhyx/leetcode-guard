import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/coach/wrapper_transport.dart';

const _rid = '01JB2Z3Y4X5W6V7T8S9R0QPNMK';
final Uri _base = Uri.parse('http://localhost:8776/');

WrapperCoachTransport _wrapper(
  Future<http.Response> Function(http.Request) handler,
) => WrapperCoachTransport(base: _base, client: MockClient(handler));

Matcher _outage(CoachOutage outage, [Object? message]) => throwsA(
  isA<CoachUnavailable>()
      .having((e) => e.outage, 'outage', outage)
      .having((e) => e.message, 'message', message ?? anything),
);

void main() {
  test('submit POSTs rid + req as JSON; 202 is "queued"', () async {
    late http.Request seen;
    final t = _wrapper((r) async {
      seen = r;
      return http.Response('{"rid": "$_rid"}', 202);
    });
    expect(t.phone, isFalse);
    expect(t.resultPollEvery, const Duration(seconds: 1));
    expect(
      await t.submit(_rid, {'kind': 'hint', 'dev': 'd', 'body': {}}),
      isNull,
    );
    expect(seen.method, 'POST');
    expect(seen.url.toString(), 'http://localhost:8776/coach/requests');
    expect(seen.headers['content-type'], startsWith('application/json'));
    expect(jsonDecode(seen.body), {
      'rid': _rid,
      'kind': 'hint',
      'dev': 'd',
      'body': <String, Object?>{},
    });
    expect(() => t.submit('../x', const {}), throwsArgumentError);
  });

  test('a done rid answers 200 with its result', () async {
    final t = _wrapper((_) async => http.Response('{"ok": true}', 200));
    expect((await t.submit(_rid, const {}))!.ok, isTrue);
    final bad = _wrapper((_) async => http.Response('[1]', 200));
    await expectLater(
      bad.submit(_rid, const {}),
      _outage(CoachOutage.network, contains('Unreadable')),
    );
  });

  test('result: null while running, the result once done', () async {
    var body = '{"result": null}';
    final t = _wrapper((r) async {
      expect(r.url.path, '/coach/requests/$_rid');
      return http.Response(body, 200);
    });
    expect(await t.result(_rid), isNull);
    body = '{"result": {"ok": false, "code": "rate_limited"}}';
    expect((await t.result(_rid))!.code, 'rate_limited');
    body = '"what"';
    await expectLater(t.result(_rid), _outage(CoachOutage.network));
  });

  test('an unknown rid (relay restarted) is "forgotten"', () async {
    final t = _wrapper((_) async => http.Response('', 404));
    await expectLater(t.result(_rid), _outage(CoachOutage.forgotten));
  });

  test('heartbeat, state and chat', () async {
    final asked = <Uri>[];
    final t = _wrapper((r) async {
      asked.add(r.url);
      return switch (r.url.path) {
        '/coach/heartbeat' => http.Response('{"beat": 9, "busy": "x"}', 200),
        '/coach/state' => http.Response('{"rev": 3, "steps": []}', 200),
        _ => http.Response('{"m0013": {"role": "coach", "text": "t"}}', 200),
      };
    });
    expect((await t.heartbeat())!.busy, 'x');
    expect((await t.state())!.rev, 3);
    expect((await t.chat(after: 'm0012')).single.text, 't');
    expect(asked.last.query, 'after=m0012');
    expect((await t.chat()).single.key, 'm0013');
    expect(asked.last.hasQuery, isFalse);
  });

  test('relay down, refused, other HTTP and no wrapper', () async {
    await expectLater(
      _wrapper((_) async => http.Response('{"code":"relay_down"}', 502))
          .heartbeat(),
      _outage(CoachOutage.relayDown, kRelayDownText),
    );
    for (final code in [400, 413, 415]) {
      await expectLater(
        _wrapper((_) async => http.Response('', code)).submit(_rid, const {}),
        _outage(CoachOutage.rejected, contains('$code')),
      );
    }
    await expectLater(
      _wrapper((_) async => http.Response('', 500)).state(),
      _outage(CoachOutage.network, 'Coach relay HTTP 500'),
    );
    await expectLater(
      _wrapper((_) async => throw http.ClientException('refused')).state(),
      _outage(CoachOutage.network, contains('refused')),
    );
    await expectLater(
      _wrapper((_) async => http.Response('{', 200)).state(),
      _outage(CoachOutage.network, contains('Unreadable')),
    );
  });

  test('chatFrom keeps valid keys in numeric order after the anchor', () {
    final chat = chatFrom({
      'm10000': {'text': 'late'},
      'm9999': {'text': 'early'},
      'bogus': {'text': 'x'},
      'm0001': 'not an object',
    }, after: 'm0001');
    expect(chat.map((m) => m.text), ['early', 'late']);
    expect(chatFrom(null), isEmpty);
    expect(
      chatFrom({'m0001': <String, Object?>{}}, after: 'junk').single.role,
      'system',
    );
  });

  test('a default client is made when none is given', () {
    expect(WrapperCoachTransport(base: _base).base, _base);
  });

  test('CoachUnavailable prints its message', () {
    expect(
      const CoachUnavailable(CoachOutage.network, 'why').toString(),
      'why',
    );
  });
}

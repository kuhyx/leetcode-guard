import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/wrapper_url_opener.dart';

void main() {
  group('WrapperUrlOpener', () {
    final base = Uri.parse('http://localhost:8776/');
    const url = 'https://leetcode.com/problems/two-sum/';

    test('POSTs the URL to the wrapper as JSON', () async {
      http.Request? sent;
      final open = WrapperUrlOpener(
        base: base,
        client: MockClient((r) async {
          sent = r;
          return http.Response('', 204);
        }),
      );
      expect(await open(Uri.parse(url)), isTrue);
      expect(sent!.method, 'POST');
      expect(sent!.url, Uri.parse('http://localhost:8776/open'));
      expect(sent!.headers['content-type'], startsWith('application/json'));
      expect(sent!.body, '{"url":"$url"}');
    });

    test('a refusal or a dead wrapper is false, not a crash', () async {
      final refused = WrapperUrlOpener(
        base: base,
        client: MockClient((_) async => http.Response('', 400)),
      );
      expect(await refused(Uri.parse(url)), isFalse);
      final dead = WrapperUrlOpener(
        base: base,
        client: MockClient((_) async => throw http.ClientException('down')),
      );
      expect(await dead(Uri.parse(url)), isFalse);
    });

    test('defaults to a real HTTP client', () {
      expect(WrapperUrlOpener(base: base).base, base);
    });
  });
}

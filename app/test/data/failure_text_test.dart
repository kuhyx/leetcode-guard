import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/failure_text.dart';

const _host = 'kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app';

/// The 2026-10-24 Pixel 6a banner, verbatim apart from the token.
final _dnsFailure = http.ClientException(
  "SocketException: Failed host lookup: '$_host' (OS Error: No address "
  'associated with hostname, errno = 7)',
  Uri.parse(
    'https://$_host/leetcode-guard/status_hash.json'
    '?auth=eyJhbGciOiJSUzI1NiJ9.SECRET.SIG',
  ),
);

Matcher _clean() => allOf(
  isNot(contains('SECRET')),
  isNot(contains('auth=')),
  isNot(contains('?')),
  isNot(contains('http')),
);

void main() {
  test('a DNS failure is "offline", with no URL or token', () {
    final text = describeFailure(_dnsFailure);
    expect(text, kOfflineText);
    expect(text, _clean());
  });

  test('refused, unreachable and reset connections are offline too', () {
    for (final message in [
      'Connection refused',
      'Network is unreachable',
      'Connection reset by peer',
      'Connection closed before full header was received',
    ]) {
      expect(describeFailure(http.ClientException(message)), kOfflineText);
    }
  });

  test('timeouts, as an exception or in the message, say so', () {
    expect(describeFailure(TimeoutException('slow')), kTimeoutText);
    expect(
      describeFailure(http.ClientException('Connection timed out')),
      kTimeoutText,
    );
  });

  test('anything else is the exception type name only', () {
    final text = describeFailure(
      http.ClientException(
        'weird',
        Uri.parse('https://db.example/x.json?auth=SECRET'),
      ),
    );
    expect(text, 'Network error (ClientException)');
    expect(describeFailure(const FormatException('x?auth=SECRET')), _clean());
  });

  test('a sign-in failure that was the network is offline, never the key', () {
    // crdt_sync wraps the ClientException, whose uri carries ?key=<api key>.
    final error = FirebaseAuthError(
      'network error trying to refresh the session: ClientException with '
      'SocketException: Failed host lookup: securetoken.googleapis.com, '
      'uri=https://securetoken.googleapis.com/v1/token?key=SECRET',
    );
    expect(describeSignInFailure(error), kOfflineText);
    expect(
      describeSignInFailure(FirebaseAuthError('TOKEN_EXPIRED ?key=SECRET')),
      allOf('Firebase sign-in failed (FirebaseAuthError)', _clean()),
    );
  });

  test('an HTTP status is named, and only the status', () {
    expect(httpFailure(401), 'Firebase answered HTTP 401');
  });

  test('scrubSecrets strips URLs, query strings, auth and JWTs', () {
    final text = scrubSecrets(
      'x https://db.example/a.json?auth=SECRET y auth=SECRET2 '
      'z eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl',
    );
    expect(text, allOf(_clean(), isNot(contains('eyJ'))));
    expect(text, startsWith('x '));
    expect(scrubSecrets('plain words'), 'plain words');
  });
}

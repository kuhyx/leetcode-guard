/// `/coach/*`: the wrapper forwards the page's coach calls to the relay on
/// loopback (`DOCS-coach-relay.md` §1, §4), so the browser, which resolves
/// nothing but loopback and only its own origin, never talks to 8777.
///
/// Verbatim means the method, path, query, `Content-Type` and body (at most
/// [kMaxCoachBody]); the Host becomes the relay's own, because the relay
/// refuses any other (DNS rebinding). Nothing else is forwarded: no cookie,
/// no other path.
library;

import 'dart:async';
import 'dart:io';

/// Where the relay listens unless `LEETCODE_COACH_RELAY_PORT` says otherwise.
const kRelayPort = 8777;

/// A coach request body larger than this is refused unread.
const int kMaxCoachBody = 16 * 1024;

/// How long the relay gets to answer one forwarded call.
const kRelayTimeout = Duration(seconds: 30);

/// The contract's answer when the relay is not listening.
const kRelayDownBody =
    '{"ok":false,"code":"relay_down","error":"coach service not running"}';

/// The relay origin for [env]'s `LEETCODE_COACH_RELAY_PORT` (the relay's
/// own test seam), else [kRelayPort].
Uri relayFromEnv(Map<String, String> env) {
  final port = int.tryParse(env['LEETCODE_COACH_RELAY_PORT'] ?? '');
  final valid = port != null && port > 0 && port < 65536;
  return Uri.parse('http://127.0.0.1:${valid ? port : kRelayPort}');
}

/// Whether [origin] is the wrapper's own page on [port].
bool _ownOrigin(String origin, int port) =>
    origin == 'http://localhost:$port' || origin == 'http://127.0.0.1:$port';

/// Forwards one `/coach/*` request to [relay]; the caller closes the
/// response.
///
/// A present, foreign `Origin` is refused: the relay's JSON-only POST
/// already needs a preflight no one grants, and this keeps another local
/// page from reading the chat. A same-origin GET carries no `Origin`.
Future<void> proxyCoach(
  HttpRequest request, {
  required Uri relay,
  required int ownPort,
  Duration timeout = kRelayTimeout,
}) async {
  final response = request.response;
  response.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
  final origin = request.headers.value('origin');
  if (origin != null && !_ownOrigin(origin, ownPort)) {
    response.statusCode = HttpStatus.forbidden;
    return;
  }
  final body = <int>[];
  await for (final chunk in request) {
    body.addAll(chunk);
    if (body.length > kMaxCoachBody) {
      response.statusCode = HttpStatus.requestEntityTooLarge;
      return;
    }
  }
  final target = relay.replace(
    path: request.uri.path,
    query: request.uri.hasQuery ? request.uri.query : null,
  );
  final client = HttpClient()..connectionTimeout = timeout;
  try {
    final out = await client.openUrl(request.method, target);
    if (request.headers.contentType case final ContentType type) {
      out.headers.contentType = type;
    }
    out
      ..contentLength = body.length
      ..add(body);
    final answer = await out.close().timeout(timeout);
    response.statusCode = answer.statusCode;
    if (answer.headers.contentType case final ContentType type) {
      response.headers.contentType = type;
    }
    await response.addStream(answer);
  } on SocketException {
    response
      ..statusCode = HttpStatus.badGateway
      ..headers.contentType = ContentType.json
      ..write(kRelayDownBody);
  } on TimeoutException {
    response.statusCode = HttpStatus.gatewayTimeout;
  } finally {
    client.close(force: true);
  }
}

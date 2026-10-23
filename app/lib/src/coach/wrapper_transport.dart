/// The desktop's path to the relay: the wrapper that served this page,
/// which forwards `/coach/*` to the relay on loopback
/// (`DOCS-coach-relay.md` §1). The browser never talks to the relay itself.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';

/// What the wrapper answers when the relay is not listening.
const kRelayDownText = 'Coach service not running';

/// [CoachTransport] over the wrapper at [base].
class WrapperCoachTransport implements CoachTransport {
  /// Creates the transport for the page origin [base].
  new({required this.base, http.Client? client})
    : _client = client ?? http.Client();

  /// The page's own origin.
  final Uri base;
  final http.Client _client;

  @override
  bool get phone => false;

  @override
  Duration get resultPollEvery => const Duration(seconds: 1);

  @override
  Future<RelayResult?> submit(String rid, Json req) async {
    final res = await _send(
      () => _client.post(
        base.resolve('/coach/requests'),
        headers: {'content-type': 'application/json'},
        body: jsonEncode({'rid': _checked(rid), ...req}),
      ),
    );
    if (res.statusCode == 202) return null;
    if (res.statusCode != 200) throw _failure(res);
    return RelayResult.tryParse(_decode(res.body)) ?? (throw _unreadable());
  }

  @override
  Future<RelayResult?> result(String rid) async {
    final res = await _send(
      () => _client.get(base.resolve('/coach/requests/${_checked(rid)}')),
    );
    if (res.statusCode == 404) {
      throw const CoachUnavailable(
        CoachOutage.forgotten,
        'The relay does not know this request',
      );
    }
    final body = readMap(_ok(res));
    if (body == null) throw _unreadable();
    return RelayResult.tryParse(body['result']);
  }

  @override
  Future<Heartbeat?> heartbeat() async =>
      Heartbeat.tryParse(_ok(await _get('/coach/heartbeat')));

  @override
  Future<CoachState?> state() async =>
      CoachState.tryParse(_ok(await _get('/coach/state')));

  @override
  Future<List<ChatMessage>> chat({String? after}) async {
    final query = after == null
        ? ''
        : '?after=${Uri.encodeQueryComponent(after)}';
    return chatFrom(_ok(await _get('/coach/chat$query')), after: after);
  }

  static String _checked(String rid) {
    if (!isUlid(rid)) throw ArgumentError.value(rid, 'rid', 'not a ULID');
    return rid;
  }

  Future<http.Response> _get(String path) =>
      _send(() => _client.get(base.resolve(path)));

  static Future<http.Response> _send(
    Future<http.Response> Function() call,
  ) async {
    try {
      return await call();
    } on http.ClientException catch (error) {
      throw CoachUnavailable(
        CoachOutage.network,
        'Desktop wrapper not reachable: ${error.message}',
      );
    }
  }

  static Object? _ok(http.Response res) {
    if (res.statusCode != 200) throw _failure(res);
    return _decode(res.body);
  }

  static Object? _decode(String body) {
    try {
      return jsonDecode(body);
    } on FormatException {
      throw _unreadable();
    }
  }

  static Object? _decodeOrNull(String body) {
    try {
      return jsonDecode(body);
    } on FormatException {
      return null;
    }
  }

  static CoachUnavailable _unreadable() => const CoachUnavailable(
    CoachOutage.network,
    'Unreadable reply from the coach relay',
  );

  static CoachUnavailable _failure(http.Response res) {
    final code = res.statusCode;
    if (code == 502) {
      return const CoachUnavailable(CoachOutage.relayDown, kRelayDownText);
    }
    if (code == 400 || code == 413 || code == 415) {
      // The relay words its refusal; the wrapper's own 413 has no body.
      final why = switch (_decodeOrNull(res.body)) {
        {'error': final String error} => ': $error',
        _ => ' (HTTP $code)',
      };
      return CoachUnavailable(
        CoachOutage.rejected,
        'The relay refused the request$why',
      );
    }
    return CoachUnavailable(CoachOutage.network, 'Coach relay HTTP $code');
  }
}

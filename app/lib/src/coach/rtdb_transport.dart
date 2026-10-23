/// The phone's path to the relay: Firebase RTDB REST under
/// `leetcode-guard/coach/` (`DOCS-coach-relay.md` §1). The phone PUTs only
/// `requests/{rid}/req`; the relay writes everything else.
///
/// `state` and `requests/{rid}/result` are JSON **string** leaves (RTDB
/// drops `null`, `[]` and `{}`), so each is decoded twice.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';

/// The contract root.
const kCoachRoot = 'leetcode-guard/coach';

/// [CoachTransport] over the shared Realtime Database.
class RtdbCoachTransport implements CoachTransport {
  /// Creates the transport; [open] gives the signed-in client.
  new({
    required this.open,
    required String databaseUrl,
    http.Client? httpClient,
  }) : databaseUrl = databaseUrl.endsWith('/')
           ? databaseUrl.substring(0, databaseUrl.length - 1)
           : databaseUrl,
       _http = httpClient ?? http.Client();

  /// Opens the signed-in client; only its token provider is used.
  final FirebaseOpener open;

  /// The regional database origin, no trailing slash.
  final String databaseUrl;
  final http.Client _http;

  @override
  bool get phone => true;

  @override
  Duration get resultPollEvery => const Duration(seconds: 2);

  @override
  Future<RelayResult?> submit(String rid, Json req) async {
    // `created` is the server's clock, so the relay can order a batch.
    final body = {
      'kind': req['kind'],
      'dev': req['dev'],
      'created': {'.sv': 'timestamp'},
      'body': req['body'],
    };
    await _call(
      'PUT',
      'requests/${_checked(rid)}/req',
      query: {'print': 'silent'},
      body: jsonEncode(body),
    );
    // The relay answers on `result`, even for a rid it already finished.
    return null;
  }

  @override
  Future<RelayResult?> result(String rid) async => RelayResult.tryParse(
    _leaf(await _get('requests/${_checked(rid)}/result')),
  );

  @override
  Future<Heartbeat?> heartbeat() async =>
      Heartbeat.tryParse(await _get('heartbeat'));

  @override
  Future<CoachState?> state() async =>
      CoachState.tryParse(_leaf(await _get('state')));

  @override
  Future<List<ChatMessage>> chat({String? after}) async {
    // `startAt` is inclusive; chatFrom drops the anchor itself.
    final query = after == null
        ? const <String, String>{}
        : {'orderBy': r'"$key"', 'startAt': jsonEncode(after)};
    return chatFrom(await _get('chat', query: query), after: after);
  }

  static String _checked(String rid) {
    if (!isUlid(rid)) throw ArgumentError.value(rid, 'rid', 'not a ULID');
    return rid;
  }

  /// A string leaf decoded once more; an object is taken as it is.
  static Object? _leaf(Object? value) {
    if (value is! String) return value;
    try {
      return jsonDecode(value);
    } on FormatException {
      throw _unreadable();
    }
  }

  Future<Object?> _get(
    String node, {
    Map<String, String> query = const {},
  }) async {
    final res = await _call('GET', node, query: query);
    try {
      return jsonDecode(res.body);
    } on FormatException {
      throw _unreadable();
    }
  }

  static CoachUnavailable _unreadable() => const CoachUnavailable(
    CoachOutage.network,
    'Unreadable coach data in Firebase',
  );

  Future<http.Response> _call(
    String method,
    String node, {
    Map<String, String> query = const {},
    String? body,
  }) async {
    final client = await open();
    if (client == null) {
      throw const CoachUnavailable(
        CoachOutage.signedOut,
        'Not signed in: connect the Sync account first',
      );
    }
    final http.Response res;
    try {
      final token = await client.auth.idToken();
      final uri = Uri.parse('$databaseUrl/$kCoachRoot/$node.json')
          .replace(queryParameters: {...query, 'auth': token});
      final request = http.Request(method, uri);
      if (body != null) {
        request
          ..headers['content-type'] = 'application/json'
          ..body = body;
      }
      res = await http.Response.fromStream(await _http.send(request));
    } on http.ClientException catch (error) {
      throw CoachUnavailable(CoachOutage.network, 'Network error: $error');
    } on RemoteSyncError catch (error) {
      throw CoachUnavailable(
        CoachOutage.signedOut,
        'Firebase sign-in failed: $error',
      );
    }
    if (res.statusCode != 200 && res.statusCode != 204) {
      throw CoachUnavailable(
        CoachOutage.network,
        'Firebase HTTP ${res.statusCode}',
      );
    }
    return res;
  }
}

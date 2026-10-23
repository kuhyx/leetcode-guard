/// How the app reaches the PC's coach relay: the wrapper on the desktop,
/// Firebase RTDB on the phone (`DOCS-coach-relay.md` §1). Both answer the
/// same shapes; everything above this seam is one code path.
library;

import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';

/// Why the relay cannot be reached right now.
enum CoachOutage {
  /// Desktop: the wrapper answered `relay_down` (the service is stopped).
  relayDown,

  /// The network, the wrapper or Firebase did not answer.
  network,

  /// Phone: no Sync account on this device.
  signedOut,

  /// The relay refused the request itself (HTTP 400 / 413 / 415).
  rejected,

  /// Desktop: the relay does not know the rid (it restarted); send it again.
  forgotten,
}

/// Raised by a [CoachTransport] call that could not be answered.
class CoachUnavailable implements Exception {
  /// Creates the error.
  const new(this.outage, this.message);

  /// Which kind of failure.
  final CoachOutage outage;

  /// Why, in words a banner can show.
  final String message;

  @override
  String toString() => message;
}

/// The relay's request, result, state, heartbeat and chat, over one path.
abstract interface class CoachTransport {
  /// Whether this is the phone's RTDB path: PC offline is then judged by
  /// the heartbeat's age, and requests carry a server timestamp.
  bool get phone;

  /// How often a request's result is polled (desktop 1 s, phone 2 s).
  Duration get resultPollEvery;

  /// Sends request [rid]: `{"kind","dev","body"}` in [req]. Returns the
  /// result when the relay already has one (a done rid), else null.
  Future<RelayResult?> submit(String rid, Json req);

  /// The result of [rid], or null while it is queued or running.
  Future<RelayResult?> result(String rid);

  /// The heartbeat, or null when the relay never wrote one.
  Future<Heartbeat?> heartbeat();

  /// The decoded `state`, or null when there is none.
  Future<CoachState?> state();

  /// Chat messages after key [after] (all when null), in key order.
  Future<List<ChatMessage>> chat({String? after});
}

/// Chat messages from a decoded `{"m0001": {...}}` map, keys validated and
/// sorted, keeping only those after [after].
List<ChatMessage> chatFrom(Object? decoded, {String? after}) {
  final map = readMap(decoded) ?? const <String, Object?>{};
  // Numeric, not string, order: `m10000` sorts after `m9999`.
  int index(String key) => int.parse(key.substring(1));
  final floor = after != null && isMessageKey(after) ? index(after) : -1;
  final keys =
      map.keys.where(isMessageKey).where((k) => index(k) > floor).toList()
        ..sort((a, b) => index(a).compareTo(index(b)));
  return [
    for (final k in keys)
      if (readMap(map[k]) case final Json m) ChatMessage.fromJson(k, m),
  ];
}

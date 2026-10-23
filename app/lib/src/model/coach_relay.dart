/// The relay's other shapes (`DOCS-coach-relay.md` §1-2): the heartbeat,
/// a chat message, a request's result and a `run_code` report.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// `heartbeat`: the relay's sign of life, every 30 s and on every change.
class Heartbeat {
  /// Parses the heartbeat object (`beat` already resolved to ms).
  new fromJson(Json json)
    : beat = readInt(json['beat']),
      stateRev = readInt(json['state_rev']),
      busy = readString(json['busy']);

  /// When the relay last beat, unix ms.
  final int? beat;

  /// The `state` revision; a move means "refetch state and chat".
  final int? stateRev;

  /// The rid running now; absent when idle.
  final String? busy;

  /// Parses a decoded heartbeat, or null when it is not an object.
  static Heartbeat? tryParse(Object? decoded) =>
      readSection(decoded, Heartbeat.fromJson);
}

/// One `chat/{m0001}` message.
class ChatMessage {
  /// Parses message [key].
  new fromJson(this.key, Json json)
    : role = readString(json['role']) ?? 'system',
      kind = readString(json['kind']) ?? 'chat',
      text = readString(json['text']) ?? '',
      at = readInt(json['at']);

  /// `m0001`, in order.
  final String key;

  /// `kuhy|coach|system`.
  final String role;

  /// `chat|hint|reveal|grade|accepted|refused|run`.
  final String kind;

  /// The text.
  final String text;

  /// Unix ms.
  final int? at;
}

/// A request's result, from either path.
class RelayResult {
  /// Parses a result object.
  new fromJson(Json json)
    : ok = readBool(json['ok']) ?? false,
      stateRev = readInt(json['state_rev']),
      data = readMap(json['data']) ?? const {},
      code = readString(json['code']),
      error = readString(json['error']),
      retry = readBool(json['retry']) ?? false,
      raw = json;

  /// Whether it worked.
  final bool ok;

  /// The `state` revision after it.
  final int? stateRev;

  /// The kind's data (ok only).
  final Json data;

  /// The error code (not ok).
  final String? code;

  /// The error, worded for kuhy.
  final String? error;

  /// Whether sending it again (as a new rid) may work.
  final bool retry;

  /// The whole object, for the error's extra fields (`note`, `resets_at`).
  final Json raw;

  /// Parses a decoded result, or null when it is not an object.
  static RelayResult? tryParse(Object? decoded) =>
      readSection(decoded, RelayResult.fromJson);
}

/// One example of a `run_code` report.
class RunExample {
  /// Parses an example.
  new fromJson(Json json)
    : n = readInt(json['n']),
      ok = readBool(json['ok']) ?? false,
      got = readString(json['got']),
      expected = readString(json['expected']);

  /// The statement's example number.
  final int? n;

  /// Whether it matched.
  final bool ok;

  /// The printed value.
  final String? got;

  /// The expected printed value.
  final String? expected;

  /// "example N: got X, expected Y" (decision 8's exact wording).
  String get line =>
      'example ${n ?? '?'}: got ${got ?? '?'}, expected ${expected ?? '?'}';
}

/// The data of a `run_code` result.
class RunReport {
  /// Parses `data`.
  new fromJson(Json json)
    : examples = readObjects(json['examples'], RunExample.fromJson) ?? const [],
      error = readString(json['error']);

  /// One line per example.
  final List<RunExample> examples;

  /// `timeout|node_missing|no_examples|syntax`, or null.
  final String? error;

  /// [error] in words, or null.
  String? get errorText => switch (error) {
    null => null,
    'timeout' => 'The run timed out (5 s)',
    'node_missing' => 'node is not installed on the PC',
    'no_examples' => 'The statement has no examples to run',
    'syntax' => 'The code does not parse',
    final String other => 'The run failed: $other',
  };
}

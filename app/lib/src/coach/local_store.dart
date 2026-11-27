/// The coach's local copy: the outbox (the one request not yet answered)
/// and the last pulled thread (state, chat, grades), kept on the device so
/// a write is never lost to the network and a cold start offline still
/// shows the session (the offline-first rule, `DOCS-coach-relay.md` §1).
///
/// Display data and the user's own words only, never a credential.
library;

import 'dart:convert';

import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Where the outbox and the thread live: one string per key, null clears.
abstract interface class CoachLocalStore {
  /// The stored value of [key], or null.
  Future<String?> read(String key);

  /// Replaces [key]'s value; null removes it.
  Future<void> write(String key, String? value);
}

/// [CoachLocalStore] in `shared_preferences` (localStorage on the web
/// build).
class PrefsCoachStore implements CoachLocalStore {
  @override
  Future<String?> read(String key) async =>
      (await SharedPreferences.getInstance()).getString(key);

  @override
  Future<void> write(String key, String? value) async {
    final prefs = await SharedPreferences.getInstance();
    await (value == null ? prefs.remove(key) : prefs.setString(key, value));
  }
}

/// [CoachLocalStore] in memory: the default when none is given, and the
/// tests' "device storage" that outlives one controller.
class MemoryCoachStore implements CoachLocalStore {
  /// The stored values.
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }
}

/// The outbox's key.
const kOutboxKey = 'coach.outbox';

/// The thread's key.
const kThreadKey = 'coach.thread';

/// [p] as stored; [sent] = the transport took it (only the result is owed).
String encodeOutbox(PendingRequest p, {required bool sent}) => jsonEncode({
  'rid': p.rid,
  'kind': p.kind,
  'body': p.body,
  'sent_at': p.sentAt.millisecondsSinceEpoch,
  'sent': sent,
});

/// The stored request, or null when there is none or it is unreadable. One
/// the transport never took comes back [RequestPhase.notSent] (sent again by
/// itself); one it took comes back queued (only its result is polled, so a
/// relay that already ran it never runs it twice).
PendingRequest? decodeOutbox(String? raw) {
  final json = readMap(_decode(raw));
  if (json == null) return null;
  final rid = readString(json['rid']);
  final kind = readString(json['kind']);
  final body = readMap(json['body']);
  final at = readInt(json['sent_at']);
  if (rid == null || !isUlid(rid) || kind == null || body == null) return null;
  final p = PendingRequest(
    rid,
    kind,
    body,
    sentAt: DateTime.fromMillisecondsSinceEpoch(at ?? 0),
  );
  if (readBool(json['sent']) != true) p.phase = RequestPhase.notSent;
  return p;
}

/// The last pulled thread.
class StoredThread {
  /// Creates the thread.
  const new(this.state, this.messages, this.grades);

  /// The relay's state, or null.
  final CoachState? state;

  /// The chat, in key order.
  final List<ChatMessage> messages;

  /// Each step's last grade data this session.
  final Map<int, Json> grades;
}

/// The thread as stored.
String encodeThread(
  CoachState? state,
  List<ChatMessage> messages,
  Map<int, Json> grades,
) => jsonEncode({
  'state': state?.raw,
  'messages': [
    for (final m in messages)
      {
        'key': m.key,
        'role': m.role,
        'kind': m.kind,
        'text': m.text,
        'at': m.at,
      },
  ],
  'grades': {for (final e in grades.entries) '${e.key}': e.value},
});

/// The stored thread, or null when there is none or it is unreadable;
/// a malformed message or grade is dropped, not the whole thread.
StoredThread? decodeThread(String? raw) {
  final json = readMap(_decode(raw));
  if (json == null) return null;
  final rows = readObjects<Json>(json['messages'], (m) => m);
  final messages = <ChatMessage>[
    for (final row in rows ?? const <Json>[])
      if (readString(row['key']) case final String key when isMessageKey(key))
        ChatMessage.fromJson(key, row),
  ];
  final grades = <int, Json>{
    for (final e
        in (readMap(json['grades']) ?? const <String, Object?>{}).entries)
      if ((int.tryParse(e.key), readMap(e.value)) case (
        final int n,
        final Json data,
      ))
        n: data,
  };
  return StoredThread(CoachState.tryParse(json['state']), messages, grades);
}

Object? _decode(String? raw) {
  if (raw == null) return null;
  try {
    return jsonDecode(raw);
  } on FormatException {
    return null;
  }
}

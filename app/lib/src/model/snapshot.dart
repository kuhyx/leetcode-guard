/// The schema-v1 snapshot the PC publishes at `leetcode-guard/status`.
///
/// Display-only by contract: nothing that decides, charges or credits ever
/// reads it, so this app can only ever be wrong about what it *shows*.
library;

import 'dart:convert';

import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/model/extras.dart';
import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:leetcode_guard/src/model/profile.dart';
import 'package:leetcode_guard/src/model/status.dart';

export 'package:leetcode_guard/src/model/coach.dart';
export 'package:leetcode_guard/src/model/extras.dart';
export 'package:leetcode_guard/src/model/profile.dart';
export 'package:leetcode_guard/src/model/status.dart';

/// One published snapshot. Every section may be null, meaning unknown.
class Snapshot {
  /// Parses a decoded snapshot object.
  new fromJson(Json json)
    : schema = readInt(json['schema']),
      generatedAt = readTime(json['generated_at']),
      status = readSection(json['status'], StatusData.fromJson),
      progress = readSection(json['progress'], Progress.fromJson),
      projectionPrice = readInt(json['projection_price']),
      projections = _projections(json['projections']),
      profile = readSection(json['profile'], ProfileData.fromJson),
      coach = readSection(json['coach'], CoachData.fromJson);

  /// Parses a response body, or null when it is not a snapshot.
  ///
  /// The node holds ONE JSON string (a tree would drop every `null` and
  /// `[]`, i.e. the "unknown" sections), so the body is decoded twice. A
  /// plain object is accepted too, for the desktop `--fixture` files.
  static Snapshot? tryParse(String body) {
    final map = readMap(_decodeLeaf(body));
    return map == null ? null : Snapshot.fromJson(map);
  }

  /// Schema version (1).
  final int? schema;

  /// When the PC built it; null when absent or unparsable (reads stale).
  final DateTime? generatedAt;

  /// The gate's answer.
  final StatusData? status;

  /// Profile solved/total.
  final Progress? progress;

  /// The Tue-Thu price the projections were computed at.
  final int? projectionPrice;

  /// Precomputed projections by target date (`YYYY-MM-DD`).
  final Map<String, Projection>? projections;

  /// The LeetCode profile view.
  final ProfileData? profile;

  /// The coach's session logs.
  final CoachData? coach;

  static Map<String, Projection>? _projections(Object? value) {
    final all = readObjectMap(value, Projection.fromJson);
    if (all == null) return null;
    return {for (final MapEntry(:key, :value) in all.entries) key: ?value};
  }
}

/// The `leetcode-guard/heartbeat` node: an ISO instant written every
/// minute, so staleness does not need the whole snapshot re-pushed.
/// Null for a missing, malformed or non-string body.
DateTime? parseHeartbeat(String? body) =>
    body == null ? null : readTime(_decodeLeaf(body));

/// [body] decoded, and decoded again when it is a JSON string leaf holding
/// JSON. Null when it is not JSON at all.
Object? _decodeLeaf(String body) {
  try {
    final decoded = jsonDecode(body);
    if (decoded is! String) return decoded;
    try {
      return jsonDecode(decoded);
    } on FormatException {
      // A string leaf that is not JSON itself (the heartbeat's timestamp).
      return decoded;
    }
  } on FormatException {
    return null;
  }
}

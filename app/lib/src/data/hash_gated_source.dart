/// The phone's cheap poll: re-download the ~32 KB status only when the
/// PC says it changed.
///
/// The exporter publishes `leetcode-guard/status_hash` beside the status,
/// so a poll costs two tiny reads (the hash, then the heartbeat the
/// controller asks for) instead of the whole snapshot every minute.
///
/// Assumes the exporter writes `status` before `status_hash`: a hash that
/// lands first could pair the new hash with the old body, which would then
/// stay on screen until the next change.
library;

import 'package:leetcode_guard/src/data/snapshot_source.dart';

/// How long a missing hash node lets the status go unre-read.
const kFullFetchFallback = Duration(minutes: 10);

/// A [SnapshotSource] that can also read the status's content hash.
abstract interface class HashedSnapshotSource implements SnapshotSource {
  /// The raw `status_hash` body, or null when the node is missing.
  ///
  /// Throws [SnapshotUnavailable] when it cannot be read.
  Future<String?> statusHash();
}

/// Wraps [inner] so [fetch] downloads the status only on first use, when
/// the hash changed, or, with no hash node, once per [kFullFetchFallback].
/// Otherwise it answers the body it already has.
class HashGatedSource implements SnapshotSource {
  /// Creates the gate over [inner]; [clock] is injected for tests.
  new(this.inner, {DateTime Function()? clock})
    : _clock = clock ?? DateTime.now;

  /// The source actually read.
  final HashedSnapshotSource inner;
  final DateTime Function() _clock;

  String? _body;
  String? _hash;
  DateTime? _fetchedAt;

  @override
  Future<String?> fetch() async {
    final hash = await inner.statusHash();
    final now = _clock();
    final last = _fetchedAt;
    final due =
        last == null ||
        (hash == null
            ? now.difference(last) >= kFullFetchFallback
            : hash != _hash);
    if (!due) return _body;
    final body = await inner.fetch();
    // Remember the hash only with the body it describes: a failed or empty
    // download leaves the old one, so the next tick tries again.
    if (body != null) {
      _body = body;
      _hash = hash;
      _fetchedAt = now;
    }
    return body;
  }

  @override
  Future<String?> heartbeat() => inner.heartbeat();
}

/// Holds the snapshot on screen and keeps it fresh.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/data/snapshot_cache.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';

/// How often the app re-reads (the PC beats once a minute).
const kPollEvery = Duration(minutes: 1);

/// Fetches, caches and ages the snapshot. A failure never clears the last
/// good copy: it sets [error], and staleness does the rest.
class StatusController extends ChangeNotifier {
  /// Creates a controller over [source] and [cache].
  new({
    required this.source,
    required this.cache,
    this.reporter,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  /// Where snapshots come from.
  final SnapshotSource source;

  /// Where the last good one is kept.
  final SnapshotCache cache;

  /// Keeps each failure and sends them on the next contact; null where
  /// there is no Firebase (the desktop wrapper).
  final ErrorReporter? reporter;
  final DateTime Function() _clock;
  Timer? _timer;

  /// The snapshot on screen, or null when none was ever read.
  Snapshot? snapshot;

  /// The last heartbeat read, or null when there is none.
  DateTime? heartbeat;

  /// Why the last refresh failed, or null when it worked.
  String? error;

  /// The current time on the injected clock.
  DateTime now() => _clock();

  /// The newest sign of life: the heartbeat (the PC re-pushes the full
  /// snapshot only when it changes) or the snapshot's own `generated_at`
  /// when there is no heartbeat or it is older.
  DateTime? get freshAt {
    final beat = heartbeat;
    final generated = snapshot?.generatedAt;
    if (beat == null || generated == null) return beat ?? generated;
    return beat.isAfter(generated) ? beat : generated;
  }

  /// Whether the banner should show: unknown age, too old, none at all, or
  /// the last refresh failed (a copy that cannot be re-checked is not
  /// vouched for, however young it is).
  bool get stale => error != null || isStale(freshAt, now());

  /// Shows the cached copy first, then refreshes from [source].
  Future<void> load() async {
    final cached = await cache.read();
    if (cached != null) snapshot = Snapshot.tryParse(cached) ?? snapshot;
    notifyListeners();
    await refresh();
  }

  /// Starts [load] and re-polls every [kPollEvery]; each tick also
  /// re-evaluates staleness, so the banner appears without a new fetch.
  void start() {
    unawaited(load());
    _timer ??= Timer.periodic(kPollEvery, (_) => unawaited(refresh()));
  }

  /// Stops polling.
  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  /// Reads the snapshot, then the heartbeat; tells [reporter] how it went.
  Future<void> refresh() async {
    String? failure;
    try {
      final body = await source.fetch();
      final parsed = body == null ? null : Snapshot.tryParse(body);
      if (body == null) {
        error = 'No snapshot published yet';
      } else if (parsed == null) {
        error = 'The published snapshot is unreadable';
      } else {
        snapshot = parsed;
        error = null;
        await cache.write(body);
      }
      heartbeat = parseHeartbeat(await source.heartbeat());
    } on SnapshotUnavailable catch (e) {
      error = failure = e.message;
    } on Exception catch (e, stack) {
      log('snapshot refresh failed', level: 900, error: e, stackTrace: stack);
      // The type only: a message can carry a URL and its `?auth=` token.
      error = failure = 'Refresh failed (${e.runtimeType})';
    }
    notifyListeners();
    final r = reporter;
    if (r == null) return;
    await (failure == null ? r.reached() : r.failed(failure));
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}

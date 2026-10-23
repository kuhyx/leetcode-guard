/// The last good snapshot, kept so an offline launch shows it as stale
/// instead of a screen of "unknown". Display data only, never a credential.
library;

import 'package:shared_preferences/shared_preferences.dart';

/// Stores the last good raw snapshot body.
abstract interface class SnapshotCache {
  /// The stored body, or null.
  Future<String?> read();

  /// Replaces the stored body.
  Future<void> write(String raw);
}

/// [SnapshotCache] in `shared_preferences` (localStorage on the web build).
class PrefsSnapshotCache implements SnapshotCache {
  static const _key = 'snapshot.last';

  @override
  Future<String?> read() async =>
      (await SharedPreferences.getInstance()).getString(_key);

  @override
  Future<void> write(String raw) async =>
      await (await SharedPreferences.getInstance()).setString(_key, raw);
}

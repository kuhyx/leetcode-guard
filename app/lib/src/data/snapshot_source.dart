/// Where a snapshot comes from: Firebase on the phone, the local wrapper on
/// the desktop. Both answer raw bodies; parsing is the controller's.
library;

/// Raised when the snapshot cannot be read right now (offline, signed out,
/// rejected). The app keeps its last good copy and shows the stale banner.
class SnapshotUnavailable implements Exception {
  /// Creates the error with a user-facing [message].
  const new(this.message);

  /// Why, in words the banner can show.
  final String message;

  @override
  String toString() => message;
}

/// Reads the published snapshot and its heartbeat.
abstract interface class SnapshotSource {
  /// The raw snapshot body, or null when nothing has been published yet.
  ///
  /// Throws [SnapshotUnavailable] when it cannot be read.
  Future<String?> fetch();

  /// The raw heartbeat body (a JSON string holding an ISO instant), or null
  /// when there is none; the app then ages the snapshot by `generated_at`.
  ///
  /// Throws [SnapshotUnavailable] when it cannot be read.
  Future<String?> heartbeat();
}

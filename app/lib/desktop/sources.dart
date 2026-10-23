/// Where the desktop wrapper gets the snapshot it serves: a file on this
/// machine, never Firebase.
///
/// The PC that exports the snapshot is the PC showing it, so the desktop
/// reads the exporter's own copy and holds no sync credential at all.
library;

import 'dart:convert';
import 'dart:io';

import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:path/path.dart' as p;

/// The exporter's local copy: the same content as the RTDB `status` leaf,
/// as a decoded object, rewritten atomically on every push attempt.
File localSnapshotFile(String home) =>
    File(p.join(home, '.local', 'share', 'leetcode_guard', 'snapshot.json'));

/// A `--fixture` file, re-read on every request so a test can rewrite it
/// (e.g. bump `generated_at`) without restarting. Missing reads as
/// "nothing published".
class FileSnapshotSource implements SnapshotSource {
  /// Creates a source over [file].
  new(this.file);

  /// The snapshot file.
  final File file;

  @override
  Future<String?> fetch() async {
    // Absent is "not exported yet"; present but unreadable is an outage.
    if (FileSystemEntity.typeSync(file.path) == FileSystemEntityType.notFound) {
      return null;
    }
    try {
      return file.readAsStringSync();
    } on FileSystemException catch (error) {
      throw SnapshotUnavailable('Cannot read ${file.path}: ${error.message}');
    }
  }

  // No heartbeat in fixture mode: the app ages the fixture by its own
  // generated_at, so rewriting that field is how a test makes it stale.
  @override
  Future<String?> heartbeat() async => null;
}

/// The live desktop source: [localSnapshotFile], re-read per request.
///
/// Its heartbeat is the file's mtime. The exporter rewrites the file on
/// every push attempt, failed pushes included, so the mtime says how
/// recently the PC last looked, which is exactly what "as of" means here.
class LocalSnapshotSource extends FileSnapshotSource {
  /// Creates the source over [file].
  new(super.file);

  @override
  Future<String?> heartbeat() async {
    final stat = file.statSync();
    if (stat.type != FileSystemEntityType.file) return null;
    return jsonEncode(stat.modified.toUtc().toIso8601String());
  }
}

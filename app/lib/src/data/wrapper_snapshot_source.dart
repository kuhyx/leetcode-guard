/// The desktop source: the local wrapper that served this page.
///
/// The wrapper does the Firebase read itself with the shared
/// `~/.config/crdt-sync/` credential, so the browser profile never holds a
/// password or refresh token (a browser cannot reach the OS keyring, and
/// web `flutter_secure_storage` keeps its wrap key beside the ciphertext).
library;

import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/snapshot_source.dart';

/// Wrapper route serving the snapshot.
const kSnapshotPath = '/snapshot.json';

/// Wrapper route serving the heartbeat.
const kHeartbeatPath = '/heartbeat.json';

/// Reads [kSnapshotPath] and [kHeartbeatPath] from the wrapper at [base].
class WrapperSnapshotSource implements SnapshotSource {
  /// Creates a source over the wrapper origin [base].
  new({required this.base, http.Client? client})
    : _client = client ?? http.Client();

  /// The page's own origin.
  final Uri base;
  final http.Client _client;

  @override
  Future<String?> fetch() => _get(kSnapshotPath);

  @override
  Future<String?> heartbeat() => _get(kHeartbeatPath);

  Future<String?> _get(String path) async {
    final http.Response res;
    try {
      res = await _client.get(base.resolve(path));
    } on http.ClientException catch (error) {
      throw SnapshotUnavailable('Desktop wrapper not reachable: $error');
    }
    if (res.statusCode == 404) return null;
    if (res.statusCode != 200) {
      throw SnapshotUnavailable('Wrapper HTTP ${res.statusCode}: ${res.body}');
    }
    return res.body;
  }
}

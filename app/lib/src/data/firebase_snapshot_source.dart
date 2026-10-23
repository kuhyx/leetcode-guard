/// Reads `leetcode-guard/status` and `leetcode-guard/heartbeat` from the
/// shared Realtime Database.
///
/// Used by the phone (client from the keystore) and by the desktop wrapper
/// (client from `~/.config/crdt-sync/`). Pure Dart, so both can share it.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/snapshot_source.dart';

/// Where the PC's exporter publishes the snapshot (one JSON string leaf).
const kStatusPath = 'leetcode-guard/status';

/// The tiny freshness node, an ISO instant written every minute.
const kHeartbeatNode = 'leetcode-guard/heartbeat';

/// Opens a signed-in client, or null when this device has no account.
typedef FirebaseOpener = Future<FirebaseRestClient?> Function();

/// Raw GETs of [kStatusPath] and [kHeartbeatNode].
///
/// Raw rather than `FirebaseRestClient.getFileText`, which would decode the
/// leaf for us: the controller parses, so the desktop wrapper can pass the
/// exact same body straight through to the browser.
class FirebaseSnapshotSource implements SnapshotSource {
  /// Creates a source over [open].
  new({
    required this.open,
    required String databaseUrl,
    http.Client? httpClient,
  }) : databaseUrl = databaseUrl.endsWith('/')
           ? databaseUrl.substring(0, databaseUrl.length - 1)
           : databaseUrl,
       _http = httpClient ?? http.Client();

  /// Opens the signed-in client; only its token provider is used.
  final FirebaseOpener open;

  /// The regional database origin, no trailing slash.
  final String databaseUrl;
  final http.Client _http;

  @override
  Future<String?> fetch() => _get(kStatusPath);

  @override
  Future<String?> heartbeat() => _get(kHeartbeatNode);

  Future<String?> _get(String path) async {
    final client = await open();
    if (client == null) {
      throw const SnapshotUnavailable(
        'Not signed in: connect the Sync account first',
      );
    }
    final http.Response res;
    try {
      final token = await client.auth.idToken();
      res = await _http.get(
        Uri.parse('$databaseUrl/$path.json')
            .replace(queryParameters: {'auth': token}),
      );
    } on http.ClientException catch (error) {
      throw SnapshotUnavailable('Network error: $error');
    } on RemoteSyncError catch (error) {
      throw SnapshotUnavailable('Firebase sign-in failed: $error');
    }
    if (res.statusCode != 200) {
      throw SnapshotUnavailable('Firebase HTTP ${res.statusCode}');
    }
    return res.body.trim() == 'null' ? null : res.body;
  }
}

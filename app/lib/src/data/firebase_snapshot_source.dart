/// Reads the sealed `status`, `status_hash` and `heartbeat` leaves under
/// `leetcode-guard/snapshot-e2e` from the shared Realtime Database.
///
/// The phone's source (client from the keystore), wrapped in a
/// `HashGatedSource` so a poll only re-downloads the status when its hash
/// moves. The desktop never reads Firebase: its wrapper serves the
/// exporter's local file.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/e2e_stores.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/data/hash_gated_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';

/// Where the PC's exporter publishes the snapshot (one sealed string leaf).
final String kStatusPath = '${kSnapshotLayout.prefix}/status';

/// The tiny freshness node, an ISO instant written every minute.
final String kHeartbeatNode = '${kSnapshotLayout.prefix}/heartbeat';

/// The status's content hash, written beside it.
final String kStatusHashNode = '${kSnapshotLayout.prefix}/status_hash';

/// Shown when this phone has no usable key; the lock button says the rest.
const kE2eLockedText = 'E2E locked';

/// Opens a signed-in client, or null when this device has no account.
typedef FirebaseOpener = Future<FirebaseRestClient?> Function();

/// Decrypted reads of [kStatusPath], [kStatusHashNode] and [kHeartbeatNode].
///
/// Each value comes back JSON-encoded, the shape a raw RTDB GET of the leaf
/// had, so the controller parses every source the same way.
class FirebaseSnapshotSource implements HashedSnapshotSource {
  /// Creates a source over [stores].
  new({required this.stores});

  /// The shared, once-unlocked sealing stores.
  final SealedStores stores;

  @override
  Future<String?> fetch() => _get(kStatusPath);

  @override
  Future<String?> heartbeat() => _get(kHeartbeatNode);

  @override
  Future<String?> statusHash() => _get(kStatusHashNode);

  Future<String?> _get(String path) async {
    final String? text;
    try {
      final store = await stores.snapshot();
      if (store == null) {
        throw const SnapshotUnavailable(
          'Not signed in: connect the Sync account first',
        );
      }
      text = await store.getFileText(path);
    } on E2eLockedFailure {
      throw const SnapshotUnavailable(kE2eLockedText);
    } on http.ClientException catch (error) {
      throw SnapshotUnavailable(describeFailure(error));
    } on RemoteSyncError catch (error) {
      throw SnapshotUnavailable(describeRemoteFailure(error));
    }
    return text == null ? null : jsonEncode(text);
  }
}

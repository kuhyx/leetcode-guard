/// The phone's half of leetcode-guard's end-to-end encryption; the PC's half
/// is `leetcode_guard/_e2e.py`, and the two must agree on every path here.
///
/// RTDB only ever holds ciphertext under:
/// * `leetcode-guard/snapshot-e2e/{status,status_hash,heartbeat}`, written
///   by the PC, read by `FirebaseSnapshotSource`;
/// * `leetcode-guard/app_errors-e2e/<device>`, written by
///   `RtdbErrorReporter`, read by the PC.
///
/// Both share one header, `leetcode-guard/e2e`, so one key opens both.
/// `leetcode-guard/coach` stays clear: utils' leetcode_coach relay reads it
/// too and moves with that repo, never alone.
///
/// **Locked fails closed**: no passphrase or a wrong one means no read and no
/// write; [SealedStores.locked] drives the icon-only passphrase button.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/failure_text.dart';

/// Never existed in clear: an empty old tree, so the one-time copy is free.
const kSnapshotOldPrefix = 'leetcode-guard/snapshot';

/// The snapshot leaves' sealed home.
final kSnapshotLayout = E2eLayout.of(kSnapshotOldPrefix);

/// The phone error reports' sealed home (same header as the snapshot).
final kAppErrorsLayout = E2eLayout.of('leetcode-guard/app_errors');

/// Opens a signed-in client, or null when this device has no account.
typedef StoreOpener = Future<RemoteStore?> Function();

/// Unlocks the snapshot layout over a signed-in client.
typedef E2eUnlocker = Future<E2eState> Function(RemoteStore client);

/// Production [E2eUnlocker]: passphrase and key cache from the keystore.
// coverage:ignore-start
Future<E2eState> unlockFromKeystore(RemoteStore client) =>
    openEncryptedStoreFromKeystore(
      store: client,
      oldPrefix: kSnapshotOldPrefix,
    );
// coverage:ignore-end

/// Thrown when this device must not touch the sealed nodes yet.
class E2eLockedFailure implements Exception {
  /// Creates the failure.
  const new();
}

/// One unlock per app run, shared by every reader and writer.
class SealedStores {
  /// Creates the stores over [open].
  new({required this.open, E2eUnlocker? unlock})
    : _unlock = unlock ?? unlockFromKeystore;

  /// Opens the signed-in client.
  final StoreOpener open;
  final E2eUnlocker _unlock;

  /// Whether the last open found no usable key.
  final ValueNotifier<bool> locked = ValueNotifier(false);

  EncryptingStore? _snapshot;
  RemoteStore? _client;

  /// The sealing store for the snapshot leaves; null when not signed in.
  ///
  /// Throws [E2eLockedFailure] when locked. Only a ready store is kept, so a
  /// passphrase saved later unlocks on the next call.
  Future<EncryptingStore?> snapshot() async {
    final cached = _snapshot;
    if (cached != null) return cached;
    final client = await open();
    if (client == null) return null;
    final state = await _unlock(client);
    if (state is! E2eReady) {
      locked.value = true;
      throw const E2eLockedFailure();
    }
    locked.value = false;
    _client = client;
    return _snapshot = state.store;
  }

  /// The sealing store for the error reports, under the same key.
  Future<EncryptingStore?> appErrors() async {
    final snap = await snapshot();
    final client = _client;
    if (snap == null || client == null) return null;
    return EncryptingStore(
      client,
      snap.key,
      pathPrefix: kAppErrorsLayout.prefix,
      revsPath: kAppErrorsLayout.revsPath,
      e2ePath: kAppErrorsLayout.e2ePath,
    );
  }

  /// Forgets the cached store, after a passphrase change.
  void reset() {
    _snapshot = null;
    _client = null;
  }
}

/// A crdt_sync store failure in the same words as a raw request's: the
/// HTTP status when there is one, else the network or sign-in wording.
/// Built from the message, which crdt_sync keeps free of the `?auth=` URL.
String describeRemoteFailure(RemoteSyncError error) {
  final status = httpStatusIn(error.message);
  if (status != null) return httpFailure(status);
  if (error.message.startsWith('network error')) {
    return describeFailure(http.ClientException(error.message));
  }
  return describeSignInFailure(error);
}

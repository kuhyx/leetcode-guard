/// Sends the phone's kept errors, sealed, to
/// `leetcode-guard/app_errors-e2e/<device id>` on the next successful
/// Firebase contact; the desktop's harvester bulk-reads that node through
/// its own sealing store and raises a notification once per new error.
///
/// One sealed JSON string leaf per install (RTDB drops nulls and empties
/// from a tree), written through the shared [SealedStores], so a locked
/// phone sends nothing rather than plaintext. Best effort throughout:
/// a failed upload only leaves the errors pending, and is never itself
/// recorded, so it cannot feed back into the banner or the log.
library;

import 'dart:developer' as developer;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:leetcode_guard/src/data/e2e_stores.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart'
    show kE2eLockedText;

/// Where each install's errors land.
final String kAppErrorsRoot = kAppErrorsLayout.prefix;

/// What the controllers tell about their Firebase contacts.
abstract interface class ErrorReporter {
  /// An error was shown: keep it.
  Future<void> failed(String message);

  /// Firebase answered: send what is kept, if anything is new. True when
  /// something was sent.
  Future<bool> reached();
}

/// [ErrorReporter] over [AppErrorLog] and RTDB REST.
class RtdbErrorReporter implements ErrorReporter {
  /// Creates the reporter; [stores] gives the sealing store.
  new({required this.log, required this.devices, required this.stores});

  /// The kept errors.
  final AppErrorLog log;

  /// This install's id, the node's key.
  final DeviceIdStore devices;

  /// The shared, once-unlocked sealing stores.
  final SealedStores stores;
  bool _sending = false;

  @override
  Future<void> failed(String message) => log.record(message);

  @override
  Future<bool> reached() async {
    if (_sending) return false;
    _sending = true;
    try {
      return await _send();
    } finally {
      _sending = false;
    }
  }

  Future<bool> _send() async {
    final device = await devices.deviceId();
    final batch = await log.pending(device);
    if (batch == null) return false;
    try {
      final store = await stores.appErrors();
      if (store == null) return false;
      await store.putFileText(
        '$kAppErrorsRoot/$device',
        batch.body,
        message: 'leetcode-guard: app errors',
      );
    } on E2eLockedFailure {
      return _gaveUp(kE2eLockedText);
    } on http.ClientException catch (error) {
      return _gaveUp(describeFailure(error));
    } on RemoteSyncError catch (error) {
      return _gaveUp(describeRemoteFailure(error));
    }
    await log.markSent(batch);
    return true;
  }

  static bool _gaveUp(String why) {
    developer.log(
      'error report not sent, kept for the next contact: $why',
      level: 900,
    );
    return false;
  }
}

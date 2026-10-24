/// Sends the phone's kept errors to `leetcode-guard/app_errors/<device id>`
/// on the next successful Firebase contact; the desktop's harvester reads
/// that node and raises a notification once per new error.
///
/// Same path to RTDB as the coach transport: the signed-in client's token,
/// a REST PUT of one JSON string leaf (RTDB drops nulls and empties from a
/// tree), `print=silent` so nothing is echoed back. Best effort throughout:
/// a failed upload only leaves the errors pending, and is never itself
/// recorded, so it cannot feed back into the banner or the log.
library;

import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';

/// Where each install's errors land.
const kAppErrorsRoot = 'leetcode-guard/app_errors';

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
  /// Creates the reporter; [open] gives the signed-in client.
  new({
    required this.log,
    required this.devices,
    required this.open,
    required String databaseUrl,
    http.Client? httpClient,
  }) : databaseUrl = databaseUrl.endsWith('/')
           ? databaseUrl.substring(0, databaseUrl.length - 1)
           : databaseUrl,
       _http = httpClient ?? http.Client();

  /// The kept errors.
  final AppErrorLog log;

  /// This install's id, the node's key.
  final DeviceIdStore devices;

  /// Opens the signed-in client; only its token provider is used.
  final FirebaseOpener open;

  /// The regional database origin, no trailing slash.
  final String databaseUrl;
  final http.Client _http;
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
    final client = await open();
    if (client == null) return false;
    final http.Response res;
    try {
      final token = await client.auth.idToken();
      res = await _http.put(
        Uri.parse('$databaseUrl/$kAppErrorsRoot/$device.json')
            .replace(queryParameters: {'print': 'silent', 'auth': token}),
        headers: {'content-type': 'application/json'},
        body: jsonEncode(batch.body),
      );
    } on http.ClientException catch (error) {
      return _gaveUp(describeFailure(error));
    } on RemoteSyncError catch (error) {
      return _gaveUp(describeSignInFailure(error));
    }
    if (res.statusCode != 200 && res.statusCode != 204) {
      return _gaveUp(httpFailure(res.statusCode));
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

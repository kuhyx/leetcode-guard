// coverage:ignore-file
// Bootstrap only: picks the platform's source and binds the plugins
// (url_launcher, the keystore) that `flutter test` has no binding for.
// Everything it wires is tested through LeetGuardApp's injected seams.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/coach/rtdb_transport.dart';
import 'package:leetcode_guard/src/coach/wrapper_transport.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:leetcode_guard/src/data/firebase_backend.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/google_sign_in_backend.dart';
import 'package:leetcode_guard/src/data/hash_gated_source.dart';
import 'package:leetcode_guard/src/data/snapshot_cache.dart';
import 'package:leetcode_guard/src/data/wrapper_snapshot_source.dart';
import 'package:leetcode_guard/src/data/wrapper_url_opener.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';
import 'package:url_launcher/url_launcher.dart';

/// Entry point.
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Desktop is this web build in a Chrome window: the wrapper that served
  // the page reads the exporter's local file, so the desktop never touches
  // Firebase or a credential. Its window resolves loopback only, so links
  // go out through the wrapper to the system (filtered) browser.
  //
  // The phone polls Firebase, re-downloading the status only when its hash
  // moves. Its errors are kept and sent to leetcode-guard/app_errors/<dev>
  // on the next contact, for the desktop to notify about.
  final devices = PrefsDeviceId();
  final reporter = kIsWeb
      ? null
      : RtdbErrorReporter(
          log: AppErrorLog(),
          devices: devices,
          open: openFirebase,
          databaseUrl: kProject.databaseUrl,
        );
  final source = kIsWeb
      ? WrapperSnapshotSource(base: Uri.base)
      : HashGatedSource(
          FirebaseSnapshotSource(
            open: openFirebase,
            databaseUrl: kProject.databaseUrl,
          ),
        );
  // The coach relay: the wrapper's /coach/* on the desktop, RTDB on the
  // phone (DOCS-coach-relay.md).
  final coach = CoachController(
    transport: kIsWeb
        ? WrapperCoachTransport(base: Uri.base)
        : RtdbCoachTransport(
            open: openFirebase,
            databaseUrl: kProject.databaseUrl,
          ),
    devices: devices,
    reporter: reporter,
  );
  runApp(
    LeetGuardApp(
      controller: StatusController(
        source: source,
        cache: PrefsSnapshotCache(),
        reporter: reporter,
      ),
      coach: coach,
      openUrl: kIsWeb
          ? WrapperUrlOpener(base: Uri.base).call
          : (uri) => launchUrl(uri, mode: LaunchMode.externalApplication),
      settingsBuilder: kIsWeb
          ? null
          : (_) => SyncSettingsScreen(
              accountLoader: loadAccount,
              accountSaver: saveAccount,
              accountClearer: clearAccount,
              sessionProbe: isFirebaseConfigured,
              firebaseFactory: openFirebase,
              googleFirebaseFactory: openFirebaseWithGoogle,
              googleAvailable: googleSignInSupported,
            ),
    ),
  );
}

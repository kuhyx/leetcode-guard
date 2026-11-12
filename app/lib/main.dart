// coverage:ignore-file
// Bootstrap only: picks the platform's source and binds the plugins
// (url_launcher, the keystore) that `flutter test` has no binding for.
// Everything it wires is tested through LeetGuardApp's injected seams.
import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart'
    show checkSyncNamespace, syncNamespace;
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show E2ePassphraseButton;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/coach/rtdb_transport.dart';
import 'package:leetcode_guard/src/coach/wrapper_transport.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:leetcode_guard/src/data/e2e_stores.dart';
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
  // Fail closed on a bad SYNC_NAMESPACE before any screen or request.
  checkSyncNamespace(syncNamespace);
  // Desktop is this web build in a Chrome window: the wrapper that served
  // the page reads the exporter's local file, so the desktop never touches
  // Firebase or a credential. Its window resolves loopback only, so links
  // go out through the wrapper to the system (filtered) browser.
  //
  // The phone polls Firebase, re-downloading the status only when its hash
  // moves. Its errors are kept and sent to leetcode-guard/app_errors-e2e/
  // <dev> on the next contact, for the desktop to notify about. Both are
  // sealed under one key, unlocked once per run (e2e_stores.dart).
  final devices = PrefsDeviceId();
  final stores = SealedStores(open: openFirebase);
  final reporter = kIsWeb
      ? null
      : RtdbErrorReporter(
          log: AppErrorLog(),
          devices: devices,
          stores: stores,
        );
  final source = kIsWeb
      ? WrapperSnapshotSource(base: Uri.base)
      : HashGatedSource(
          FirebaseSnapshotSource(stores: stores),
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
  final status = StatusController(
    source: source,
    cache: PrefsSnapshotCache(),
    reporter: reporter,
  );
  runApp(
    LeetGuardApp(
      controller: status,
      lockAction: kIsWeb
          ? null
          : ValueListenableBuilder<bool>(
              valueListenable: stores.locked,
              builder: (_, locked, _) => E2ePassphraseButton(
                locked: locked,
                onSaved: () {
                  stores.reset();
                  unawaited(status.refresh());
                },
              ),
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

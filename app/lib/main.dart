// coverage:ignore-file
// Bootstrap only: picks the platform's source and binds the plugins
// (url_launcher, the keystore) that `flutter test` has no binding for.
// Everything it wires is tested through LeetGuardApp's injected seams.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/data/firebase_backend.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/snapshot_cache.dart';
import 'package:leetcode_guard/src/data/wrapper_snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';
import 'package:url_launcher/url_launcher.dart';

/// Entry point.
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Desktop is this web build in a Chrome window: the wrapper that served
  // the page reads Firebase itself, so the browser holds no credential.
  final source = kIsWeb
      ? WrapperSnapshotSource(base: Uri.base)
      : FirebaseSnapshotSource(
          open: openFirebase,
          databaseUrl: kProject.databaseUrl,
        );
  runApp(
    LeetGuardApp(
      controller: StatusController(source: source, cache: PrefsSnapshotCache()),
      openUrl: (uri) => launchUrl(uri, mode: LaunchMode.externalApplication),
      settingsBuilder: kIsWeb
          ? null
          : (_) => const SyncSettingsScreen(
              accountLoader: loadAccount,
              accountSaver: saveAccount,
              accountClearer: clearAccount,
              sessionProbe: isFirebaseConfigured,
              firebaseFactory: openFirebase,
            ),
    ),
  );
}

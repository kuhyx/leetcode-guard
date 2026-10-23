/// Finding and launching the Chrome window the desktop app runs in.
library;

import 'dart:io';

import 'package:leetcode_guard/desktop/display_scale.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';
import 'package:path/path.dart' as p;

/// Browser profile for the app. Fixed: the profile holds the cached
/// snapshot, so a moving profile is an empty app until the first fetch.
String profileDir(String home) =>
    p.join(home, '.local', 'share', 'leetcode-guard-app', 'profile');

/// The first Chrome-family browser on this machine, or ''.
///
/// Broad on purpose: this machine runs Thorium behind /opt/google/chrome and
/// has a policy that uninstalls `chromium`. `$LEETCODE_GUARD_BROWSER`
/// overrides.
String findBrowser({String? override, bool Function(String path)? exists}) {
  final candidates = [
    override ?? Platform.environment['LEETCODE_GUARD_BROWSER'] ?? '',
    '/opt/google/chrome/chrome',
    '/opt/thorium-browser/thorium-browser',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/brave',
  ];
  return candidates.firstWhere(
    (path) => path.isNotEmpty && (exists ?? (x) => File(x).existsSync())(path),
    orElse: () => '',
  );
}

/// Every hostname but loopback fails to resolve in the app window.
///
/// The window is a bare Chrome profile without kuhy's forced LeechBlock /
/// uBlock setup, so a Ctrl+N or a link opened in it would otherwise be a
/// free, unfiltered browser. Suggestion links go out through the wrapper's
/// `POST /open` instead. `localhost` is excluded by name because `MAP *`
/// matches it before the `127.0.0.1` exclusion is consulted, and the app's
/// own origin is `http://localhost:8776` (measured 2026-10-23: without it
/// the window itself fails with ERR_NAME_NOT_RESOLVED; IP literals such as
/// `http://1.1.1.1/` fail too). One argv element: no shell, no quotes.
const kLoopbackOnly =
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, '
    'EXCLUDE 127.0.0.1';

/// Arguments for the app window, rendered at device [scale]
/// (`display_scale.dart`).
List<String> browserArgs(
  String home, {
  int port = kWrapperPort,
  double scale = 1,
}) => [
  '--app=http://localhost:$port',
  // Fixed per launch; Ctrl+= / Ctrl+- zoom on top of it, kept per origin.
  scaleFlag(scale),
  kLoopbackOnly,
  // A configured proxy resolves names itself, past the rules above.
  '--no-proxy-server',
  // Chrome lists --host-resolver-rules as an "unsupported command-line
  // flag" and pins a warning infobar over the app on every launch
  // (measured 2026-10-23); --test-type is what suppresses that infobar.
  '--test-type',
  '--user-data-dir=${profileDir(home)}',
  // WM_CLASS, matched by a .desktop entry's StartupWMClass.
  '--class=leetcode-guard-app',
  '--no-first-run',
  // Keeps Chrome off the GNOME keyring: a locked keyring blocks the first
  // page load behind an unlock prompt on another workspace.
  '--password-store=basic',
];

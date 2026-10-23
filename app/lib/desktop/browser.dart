/// Finding and launching the Chrome window the desktop app runs in.
library;

import 'dart:io';

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

/// Arguments for the app window.
List<String> browserArgs(String home, {int port = kWrapperPort}) => [
  '--app=http://localhost:$port',
  '--user-data-dir=${profileDir(home)}',
  // WM_CLASS, matched by a .desktop entry's StartupWMClass.
  '--class=leetcode-guard-app',
  '--no-first-run',
  // Keeps Chrome off the GNOME keyring: a locked keyring blocks the first
  // page load behind an unlock prompt on another workspace.
  '--password-store=basic',
];

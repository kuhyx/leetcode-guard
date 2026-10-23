/// `leetcode-guard-app`: serve the web build, open it in a Chrome app window.
///
/// Only wiring: every decision lives in `lib/desktop/launcher.dart`.
///
/// Build the page it serves with
/// `flutter build web --release --no-web-resources-cdn`: without the flag
/// CanvasKit loads from a CDN, and an offline launch renders a blank window
/// instead of the cached snapshot under the stale banner.
///
/// It serves `~/.local/share/leetcode_guard/snapshot.json`, the exporter's
/// local copy; nothing here reads Firebase. `tool/leetcode_guard_app.sh` is
/// the launcher (build if missing, start the wrapper, open the window).
///
/// Dev: `dart run bin/leetcode_guard_desktop.dart --fixture f.json` serves
/// that snapshot instead; add `--serve-only` to skip the window.
library;

import 'dart:io';

import 'package:leetcode_guard/desktop/launcher.dart';
import 'package:path/path.dart' as p;

Future<void> main(List<String> args) => runDesktop(
  args,
  home: Platform.environment['HOME'] ?? '',
  exeDir: p.dirname(Platform.resolvedExecutable),
  cwd: Directory.current.path,
);

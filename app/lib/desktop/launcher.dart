/// The desktop launcher's logic, kept out of `bin/` so it is testable.
///
/// The server outlives the browser on purpose: Chrome exits at once when it
/// hands the URL to an instance that already owns the profile, so an early
/// exit is a handoff, not "the user closed the window".
library;

import 'dart:io';

import 'package:leetcode_guard/desktop/browser.dart';
import 'package:leetcode_guard/desktop/sources.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:path/path.dart' as p;

/// Starts serving. Replaced in tests.
typedef ServerStarter = Future<void> Function(
  String webRoot,
  SnapshotSource source,
);

/// Starts the browser process. Replaced in tests.
typedef ProcessStarter = Future<Process> Function(
  String executable,
  List<String> args,
);

/// The real starter: a [WrapperServer] on [port] (0 = any, for tests).
Future<WrapperServer> startWrapper(
  String webRoot,
  SnapshotSource source, {
  int port = kWrapperPort,
}) async {
  final server = WrapperServer(webRoot: webRoot, source: source);
  await server.start(port: port);
  return server;
}

/// The file after `--fixture`, or null. Dev only: serves that snapshot
/// instead of the exporter's file, for screenshots and offline checks.
String? fixtureArg(List<String> args) {
  final at = args.indexOf('--fixture');
  return at >= 0 && at + 1 < args.length ? args[at + 1] : null;
}

/// Where the web build is: next to the installed binary (`bundle/web`), or
/// `build/web` under [cwd] for a source run.
String resolveWebRoot({required String exeDir, required String cwd}) {
  final bundled = p.normalize(p.join(exeDir, '..', 'web'));
  return Directory(bundled).existsSync()
      ? bundled
      : p.join(cwd, 'build', 'web');
}

/// Runs the desktop app: serve, then open the app window and stay alive.
///
/// `--serve-only` skips the window; `--window-only` skips serving (the
/// launcher script started the wrapper already); `--fixture <file>` swaps
/// the source. Only a process that is serving stays alive after its
/// window closes: one that found the port taken has nothing to keep up.
Future<void> runDesktop(
  List<String> args, {
  required String home,
  required String exeDir,
  required String cwd,
  ServerStarter startServer = _serve,
  String Function() browserFinder = findBrowser,
  ProcessStarter startProcess = Process.start,
  Future<void> Function() hold = _keepServing,
  void Function(String line) err = _stderr,
}) async {
  var serving = false;
  if (!args.contains('--window-only')) {
    final fixture = fixtureArg(args);
    final source = fixture == null
        ? LocalSnapshotSource(localSnapshotFile(home))
        : FileSnapshotSource(File(fixture));
    try {
      await startServer(resolveWebRoot(exeDir: exeDir, cwd: cwd), source);
      serving = true;
    } on SocketException {
      // Already serving: just open another window onto it.
      err('leetcode-guard app: already running on :$kWrapperPort');
    }
  }
  if (args.contains('--serve-only')) return;
  final browser = browserFinder();
  if (browser.isEmpty) {
    err(
      'leetcode-guard app: no Chrome-family browser found; open '
      'http://localhost:$kWrapperPort or set LEETCODE_GUARD_BROWSER',
    );
    return;
  }
  final process = await startProcess(browser, browserArgs(home));
  await process.exitCode;
  if (serving) await hold();
}

// coverage:ignore-start
// Production defaults that tests always replace: binding the fixed port (a
// test must not take it; startWrapper is covered on port 0), waiting a year
// so the wrapper keeps serving a handed-off window, and writing to stderr.
Future<void> _serve(String root, SnapshotSource source) =>
    startWrapper(root, source).then((_) {});

Future<void> _keepServing() => Future<void>.delayed(const Duration(days: 365));

void _stderr(String line) => stderr.writeln(line);
// coverage:ignore-end

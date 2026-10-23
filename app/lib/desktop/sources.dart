/// Where the desktop wrapper gets the snapshot it serves.
library;

import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:path/path.dart' as p;

/// A `--fixture` file, re-read on every request so a test can rewrite it
/// (e.g. bump `generated_at`) without restarting. Missing reads as
/// "nothing published".
class FileSnapshotSource implements SnapshotSource {
  /// Creates a source over [file].
  new(this.file);

  /// The fixture.
  final File file;

  @override
  Future<String?> fetch() async =>
      file.existsSync() ? file.readAsStringSync() : null;

  // No heartbeat in fixture mode: the app ages the fixture by its own
  // generated_at, so rewriting that field is how a test makes it stale.
  @override
  Future<String?> heartbeat() async => null;
}

/// The live source: Firebase, signed in with the machine's shared
/// `~/.config/crdt-sync/` credential (`firebase.json` + `password`), the
/// same files the Python side reads.
///
/// The config is read on first use, not at startup, so a missing file is a
/// banner in the app rather than a wrapper that refuses to start. The
/// session lives in memory: one sign-in per wrapper process.
class LiveSnapshotSource implements SnapshotSource {
  /// Creates a source reading the credential under [home].
  new(this.home, {this.httpClient});

  /// `$HOME`.
  final String home;

  /// Injected for tests.
  final http.Client? httpClient;
  final _store = InMemoryCredentialStore();
  FirebaseSnapshotSource? _inner;

  String get _dir => p.join(home, '.config', 'crdt-sync');

  @override
  Future<String?> fetch() async => await (_inner ??= _open()).fetch();

  @override
  Future<String?> heartbeat() async => await (_inner ??= _open()).heartbeat();

  FirebaseSnapshotSource _open() {
    final FirebaseConfig config;
    final String password;
    try {
      config = FirebaseConfig.parse(
        File(p.join(_dir, 'firebase.json')).readAsStringSync(),
      );
      password = File(p.join(_dir, 'password')).readAsStringSync().trim();
    } on Exception catch (error) {
      throw SnapshotUnavailable('No usable sync credential in $_dir: $error');
    }
    return FirebaseSnapshotSource(
      open: () => firebaseClientFor(
        config: config,
        store: _store,
        password: password,
        httpClient: httpClient,
      ),
      databaseUrl: config.databaseUrl,
      httpClient: httpClient,
    );
  }
}

/// The live source for [home].
SnapshotSource crdtSyncSource(String home, {http.Client? httpClient}) =>
    LiveSnapshotSource(home, httpClient: httpClient);

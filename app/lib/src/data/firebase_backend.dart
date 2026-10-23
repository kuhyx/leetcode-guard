// coverage:ignore-file
// Platform glue: every function here reaches the OS keystore through a
// platform channel `flutter test` has no binding for. The logic it wires
// (sign-in, token refresh, account parsing) lives in crdt_sync and is
// covered there; the snapshot read is FirebaseSnapshotSource, covered here.

/// The phone's Firebase wiring, copied from home-guard's
/// `firebase_backend.dart`: Google sign-in first (the sync account is
/// Google-only), the password path kept as home-guard keeps it.
///
/// * [kProject] holds the Web API key and database URL: public identifiers
///   that ship inside every APK; the security rules protect the data.
/// * The session (refresh token) and account marker live in the OS
///   keystore, written by the shared Sync settings screen.
///
/// Nothing here reads `~/.config/crdt-sync/`; on Android there is no such
/// file. The desktop never reads Firebase at all: its wrapper serves the
/// exporter's local file (`lib/desktop/sources.dart`).
library;

import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/google_sign_in_backend.dart';

/// The shared `kuhy-syncs` project. `databaseUrl` is the **regional** host:
/// the plain `*.firebaseio.com` form answers 404 with a `correctUrl` body,
/// which reads like an auth failure.
const kProject = FirebaseProject(
  apiKey: 'AIzaSyCF_sA3xCMehAYXK8eND-rAygb9NXXW_8E',
  databaseUrl:
      'https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app',
);

const _secure = FlutterSecureStorage();

/// The keystore-backed home for the Firebase refresh token.
SecureCredentialStore credentialStore() => SecureCredentialStore(
  read: (key) => _secure.read(key: key),
  write: (key, value) => _secure.write(key: key, value: value),
  delete: (key) => _secure.delete(key: key),
);

/// Reads the per-device account, or null when sync has not been set up.
Future<FirebaseAccount?> loadAccount() async {
  try {
    return FirebaseAccount.tryParse(
      await _secure.read(key: kFirebaseAccountKey),
    );
  } on Object {
    return null;
  }
}

/// Stores the per-device account. Keystore only, never prefs or source.
Future<void> saveAccount(FirebaseAccount account) =>
    _secure.write(key: kFirebaseAccountKey, value: account.toJsonString());

/// Forgets the account and any cached session.
Future<void> clearAccount() async {
  await _secure.delete(key: kFirebaseAccountKey);
  await credentialStore().clear();
}

/// Reads the account from the keystore only, with no fallback, so a value
/// just written can be read back as itself.
Future<FirebaseAccount?> storedAccount() async =>
    FirebaseAccount.tryParse(await _secure.read(key: kFirebaseAccountKey));

/// Whether this device can authenticate: a stored refresh token is what
/// signs requests, so it decides, not the account marker.
///
/// A marker with no session behind it cannot sign a single request: drop
/// just the marker so the settings screen offers a sign-in instead of a dead
/// banner (home-guard's fix for the same state).
Future<bool> isFirebaseConfigured() async {
  try {
    final auth = FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    );
    if (await auth.hasSession()) return true;
    if (await storedAccount() == null) return false;
    await _secure.delete(key: kFirebaseAccountKey);
    return false;
  } on Object catch (error, stackTrace) {
    log(
      'session probe failed; reporting this device as not configured',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return false;
  }
}

/// Signs in with Google alone, for a device with no account stored yet.
///
/// Returns null when the picker is dismissed; throws [FirebaseAuthError]
/// when Google resolves to a uid other than [kSyncUid], which would
/// otherwise authenticate fine and be denied every read.
Future<FirebaseRestClient?> openFirebaseWithGoogle({
  Future<String?> Function()? tokenFetcher,
  Future<void> Function(FirebaseAccount)? accountSaver,
  http.Client? httpClient,
}) async {
  final token = await (tokenFetcher ?? googleIdToken)();
  if (token == null) return null;
  final auth = FirebaseTokenProvider(
    apiKey: kProject.apiKey,
    store: credentialStore(),
    httpClient: httpClient,
  );
  final email = await auth.signInWithGoogle(
    idToken: token,
    expectedUid: kSyncUid,
  );
  // Saved unconditionally: `signInWithIdp` omits `email` when the account
  // hides it, and the refresh token (already stored) is the credential.
  await (accountSaver ?? saveAccount)(
    FirebaseAccount(email: email ?? '', password: ''),
  );
  return FirebaseRestClient(databaseUrl: kProject.databaseUrl, auth: auth);
}

/// A signed-in client, or null when this phone has no account yet.
///
/// Signs in with the stored password only when no refresh token is cached,
/// so the usual path costs no authentication round trip.
Future<FirebaseRestClient?> openFirebase() async {
  final account = await loadAccount();
  if (account == null) {
    final auth = FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    );
    if (!await auth.hasSession()) return null;
    return FirebaseRestClient(databaseUrl: kProject.databaseUrl, auth: auth);
  }
  try {
    return await firebaseClientFor(
      config: kProject.configFor(account.email),
      store: credentialStore(),
      password: account.password.isEmpty ? null : account.password,
    );
  } on Object {
    return null;
  }
}

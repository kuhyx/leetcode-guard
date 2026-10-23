// coverage:ignore-file
// Platform glue: every function here reaches the OS keystore through a
// platform channel `flutter test` has no binding for. The logic it wires
// (sign-in, token refresh, account parsing) lives in crdt_sync and is
// covered there; the snapshot read is FirebaseSnapshotSource, covered here.

/// The phone's Firebase wiring, copied from home-guard's
/// `firebase_backend.dart` minus Google sign-in (a new package id has no
/// OAuth client, and registering one has no API).
///
/// * [kProject] holds the Web API key and database URL: public identifiers
///   that ship inside every APK; the security rules protect the data.
/// * The account email and password are entered once per device on the
///   shared Sync settings screen and kept in the OS keystore.
///
/// Nothing here reads `~/.config/crdt-sync/`: that is the desktop wrapper's
/// half (`lib/desktop/sources.dart`). On Android there is no such file.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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

/// Whether a refresh token is stored: that, not the account marker, is
/// what signs requests.
Future<bool> isFirebaseConfigured() async {
  try {
    return await FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    ).hasSession();
  } on Object {
    return false;
  }
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

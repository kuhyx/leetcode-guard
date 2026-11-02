/// One-tap Google sign-in, ported from home-guard's
/// `google_sign_in_backend.dart`.
///
/// Its own file because `crdt_sync` is deliberately pure Dart: the plugin
/// lives in the app, and the library only ever receives a token string
/// through a closure.
///
/// The sync account is Google-only (its shared password is dead), so on a
/// fresh install this is the path that works; the password form stays on the
/// shared settings screen as home-guard keeps it.
///
/// Registered with no console visit: `firebase apps:create ANDROID` plus
/// `apps:android:sha:create` (release + debug SHA-1, read with `keytool`)
/// made Firebase auto-create this package's Android OAuth clients.
library;

import 'package:google_account_token/google_account_token.dart' as plugin;

/// The account the security rules pin.
///
/// Not a secret (it is in the public rules), but it makes a wrong-account
/// sign-in *fail loudly* instead of authenticating fine and then being
/// denied every read and write.
const kSyncUid = 'OvA2REQyLIhAHOEjzwS1o877rgG3';

/// The `kuhy-syncs` **Web** OAuth client id, the audience of the ID token.
///
/// Public by design, like the project's `apiKey`. A plain const rather than a
/// `--dart-define`, so a bare `flutter build apk` cannot ship a button that
/// always reports "cancelled". Android must request a token minted for the
/// *web* client (`client_type: 3` in `firebase apps:sdkconfig ANDROID`); an
/// Android client id here yields `audience mismatch`.
const kServerClientId =
    '845446124781-prdoherj0v64vc6egvvcp3l0693khaur.apps.googleusercontent.com';

/// Whether programmatic sign-in can work here with [serverClientId].
///
/// Only Android has an AccountManager (the plugin's own gate). The desktop is
/// the web build, where there is no account chooser, so the button must not
/// exist there; the plugin's check also keeps the web import graph free of
/// `dart:io`.
bool googleSignInAvailable({String serverClientId = kServerClientId}) =>
    plugin.googleAccountTokenSupported && serverClientId.isNotEmpty;

/// [googleSignInAvailable] for the compiled-in client id.
bool get googleSignInSupported => googleSignInAvailable();

/// Returns a Google ID token for the picked account, or null.
///
/// Null rather than throwing when the user dismisses the picker: cancelling
/// is an ordinary outcome. [signInFn] and [serverClientId] exist for tests
/// that bypass the plugin.
Future<String?> googleIdToken({
  Future<String?> Function()? signInFn,
  String serverClientId = kServerClientId,
}) async {
  if (signInFn != null) return await signInFn();
  return await plugin.googleIdToken(serverClientId: serverClientId);
}

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

import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';

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
/// Only Android ships the Credential Manager flow. The desktop is the web
/// build, where `authenticate()` throws `UnimplementedError` (an `Error`
/// that escapes an ordinary catch), so the button must not exist there.
/// A platform check through `foundation` rather than `dart:io`, because the
/// web app's import graph must stay free of `dart:io`.
bool googleSignInAvailable({String serverClientId = kServerClientId}) =>
    !kIsWeb &&
    defaultTargetPlatform == TargetPlatform.android &&
    serverClientId.isNotEmpty;

/// [googleSignInAvailable] for the compiled-in client id.
bool get googleSignInSupported => googleSignInAvailable();

/// Returns a Google ID token for the picked account, or null.
///
/// Null rather than throwing when the user dismisses the picker: cancelling
/// is an ordinary outcome. [signInFn] and [serverClientId] exist for tests,
/// which cannot reach the plugin's platform channel.
Future<String?> googleIdToken({
  Future<String?> Function()? signInFn,
  String serverClientId = kServerClientId,
}) async {
  if (signInFn != null) return await signInFn();
  if (serverClientId.isEmpty) {
    log('Google sign-in unavailable: no server client id', level: 900);
    return null;
  }
  // The plugin reaches the OS account picker through a platform channel,
  // which `flutter test` has no binding for. Everything above is covered.
  // coverage:ignore-start
  try {
    await GoogleSignIn.instance.initialize(serverClientId: serverClientId);
    if (!GoogleSignIn.instance.supportsAuthenticate()) {
      log('Google sign-in is not available on this platform', level: 900);
      return null;
    }
    final account = await GoogleSignIn.instance.authenticate();
    return account.authentication.idToken;
  } on GoogleSignInException catch (error, stackTrace) {
    // Includes a dismissed picker, but also a configuration failure
    // (unregistered SHA-1, wrong client id), which arrives the same way.
    log(
      'Google sign-in did not complete',
      level: 900,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
  // coverage:ignore-end
}

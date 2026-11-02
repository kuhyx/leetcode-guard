import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/google_sign_in_backend.dart';

const _channel = MethodChannel('dev.kuhy/google_account_token');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, null);
  });

  group('googleIdToken', () {
    test('returns the token the sign-in function yields', () async {
      // The injected path: the closure is what feeds crdt_sync, and no
      // platform channel is touched to get there.
      expect(await googleIdToken(signInFn: () async => 'a-token'), 'a-token');
    });

    test('passes a null cancellation straight through', () async {
      // Dismissing the picker is an ordinary outcome, not an error.
      expect(await googleIdToken(signInFn: () async => null), isNull);
    });

    test('reports "not configured" when the client id is missing', () async {
      // Passed explicitly: an empty id must not reach the OS chooser.
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(await googleIdToken(serverClientId: ''), isNull);
    });

    test('asks the account-token plugin for the Web client id', () async {
      // The real path: the plugin's channel gets the pinned Web client id.
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      Object? sent;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
            sent = call.arguments;
            return 'plugin-token';
          });
      expect(await googleIdToken(), 'plugin-token');
      expect(sent, {'serverClientId': kServerClientId});
    });
  });

  group('constants', () {
    test('pins the uid the security rules expect', () {
      // If this drifts from the rules, a Google sign-in is accepted and then
      // denied every read and write.
      expect(kSyncUid, 'OvA2REQyLIhAHOEjzwS1o877rgG3');
    });

    test('requests tokens for the kuhy-syncs Web client', () {
      // The Web (client_type 3) id from `firebase apps:sdkconfig ANDROID`;
      // an Android client id here yields `audience mismatch`.
      expect(
        kServerClientId,
        '845446124781-prdoherj0v64vc6egvvcp3l0693khaur'
        '.apps.googleusercontent.com',
      );
    });
  });

  group('googleSignInSupported', () {
    test('is true on Android', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(googleSignInSupported, isTrue);
    });

    test('is false off Android (the desktop is the web build)', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.linux;
      expect(googleSignInSupported, isFalse);
    });

    test('is false without a client id: a button that cannot succeed', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(googleSignInAvailable(serverClientId: ''), isFalse);
    });
  });
}

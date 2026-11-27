import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/external_launch.dart';
import 'package:url_launcher/url_launcher.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('tutorUri', () {
    test('maps a learn route onto the tutor scheme', () {
      expect(tutorUri('/learn/s/m').toString(), 'kuhytutor://learn/s/m');
    });

    test('maps a review route onto the tutor scheme', () {
      expect(tutorUri('/review/s/m').toString(), 'kuhytutor://review/s/m');
    });

    test('refuses anything but a learn or review route', () {
      for (final route in [
        null,
        '',
        'learn/s/m',
        '/settings',
        '/learn',
        '//evil.example/learn/s/m',
        '/learn/s m/x',
      ]) {
        expect(tutorUri(route), isNull, reason: '$route');
      }
    });
  });

  group('openExternally', () {
    test('hands the URI to the OS as an external application', () async {
      final calls = <(Uri, LaunchMode)>[];
      final uri = Uri.parse('https://leetcode.com/problems/two-sum/');
      final ok = await openExternally(
        uri,
        launch: (u, {mode = LaunchMode.platformDefault}) async {
          calls.add((u, mode));
          return true;
        },
      );
      expect(ok, isTrue);
      expect(calls, [(uri, LaunchMode.externalApplication)]);
    });

    test('a tutor link goes to the tutor package, never a chooser', () async {
      final calls = <(Uri, String)>[];
      final uri = Uri.parse('kuhytutor://review/s/m');
      final ok = await openExternally(
        uri,
        launch: (_, {mode = LaunchMode.platformDefault}) =>
            fail('a tutor link must not go through the scheme'),
        viaPackage: (u, package) async {
          calls.add((u, package));
          return true;
        },
      );
      expect(ok, isTrue);
      expect(calls, [(uri, kTutorPackage)]);
    });

    test('no tutor installed is a false, not an error', () async {
      for (final error in [
        PlatformException(code: 'ACTIVITY_NOT_FOUND'),
        MissingPluginException(),
      ]) {
        final ok = await openExternally(
          Uri.parse('kuhytutor://learn/s/m'),
          viaPackage: (_, _) => throw error,
        );
        expect(ok, isFalse, reason: '$error');
      }
    });

    test('the default opener asks the activity over its channel', () async {
      final seen = <MethodCall>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(kOpenChannel, (call) async {
            seen.add(call);
            return (call.arguments as Map)['package'] == kTutorPackage;
          });
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(kOpenChannel, null),
      );
      final uri = Uri.parse('kuhytutor://learn/s/m');
      expect(await openInPackage(uri, kTutorPackage), isTrue);
      expect(await openInPackage(uri, 'com.other'), isFalse);
      expect(seen.first.method, 'view');
      expect(seen.first.arguments, {
        'url': 'kuhytutor://learn/s/m',
        'package': kTutorPackage,
      });
    });

    test('no app for the scheme is a false, not an error', () async {
      final ok = await openExternally(
        Uri.parse('https://leetcode.com/problems/two-sum/'),
        launch: (_, {mode = LaunchMode.platformDefault}) =>
            throw PlatformException(code: 'ACTIVITY_NOT_FOUND'),
      );
      expect(ok, isFalse);
    });
  });
}

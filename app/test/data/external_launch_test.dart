import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/external_launch.dart';
import 'package:url_launcher/url_launcher.dart';

void main() {
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

    test('no app for the scheme is a false, not an error', () async {
      final ok = await openExternally(
        Uri.parse('kuhytutor://learn/s/m'),
        launch: (_, {mode = LaunchMode.platformDefault}) =>
            throw PlatformException(code: 'ACTIVITY_NOT_FOUND'),
      );
      expect(ok, isFalse);
    });
  });
}

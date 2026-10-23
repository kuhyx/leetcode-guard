import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// The phone this tab was reported broken on.
const kPhoneCoach = Size(412, 915);
const kTallCoach = Size(412, 6000);

Future<void> openCoach(WidgetTester tester) async {
  await tester.tap(find.text('Coach'));
  await tester.pumpAndSettle();
}

/// Records what the app writes to the clipboard.
List<String> recordClipboard(WidgetTester tester) {
  final copied = <String>[];
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    SystemChannels.platform,
    (call) async {
      if (call.method == 'Clipboard.setData') {
        copied.add((call.arguments as Map)['text'] as String);
      }
      return null;
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      null,
    ),
  );
  return copied;
}

String snapshotWith(String coach) =>
    '{"schema": 1, "generated_at": "2026-10-23T14:05:00+02:00", '
    '"coach": $coach}';

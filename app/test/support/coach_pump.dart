import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// The phone this tab was reported broken on.
const kPhoneCoach = Size(412, 915);
const kTallCoach = Size(412, 6000);

/// Taps the Coach destination by its icon (the nav paints no words).
Future<void> openCoach(WidgetTester tester) async {
  await tester.tap(find.byIcon(Icons.school_outlined).first);
  await tester.pumpAndSettle();
}

/// Taps the "Show all" style button keyed [key] and shows its sheet.
Future<void> openSheet(WidgetTester tester, Key key) async {
  await tester.tap(find.byKey(key));
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

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';

import 'fakes.dart';
import 'fixtures.dart';

/// Phone portrait, the primary platform.
const kPhone = Size(390, 844);

/// A wide desktop window.
const kDesktop = Size(1400, 900);

/// Pumps the app over [answers] (fixture names are read as bodies).
Future<StatusController> pumpApp(
  WidgetTester tester, {
  List<Object?> answers = const ['snapshot_full'],
  Size size = kPhone,
  int minutes = 1,
  List<Uri>? opened,
  WidgetBuilder? settingsBuilder,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final controller = StatusController(
    source: FakeSource([
      for (final a in answers)
        if (a is String && a.startsWith('snapshot_')) fixtureText(a) else a,
    ]),
    cache: MemoryCache(),
    clock: clockAfter(minutes),
  );
  await tester.pumpWidget(
    LeetGuardApp(
      controller: controller,
      openUrl: (uri) async {
        opened?.add(uri);
        return true;
      },
      settingsBuilder: settingsBuilder,
    ),
  );
  await tester.pumpAndSettle();
  return controller;
}

/// Scrolls the visible list until [finder] is on screen.
Future<void> reveal(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    300,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

// The Status tab paints no words (textgate, 2026-11-08): everything drawn
// is an icon, a number, a date or content LeetCode / the PC published.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/ui/projection_section.dart';
import 'package:leetcode_guard/src/ui/tabs.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';

final _word = RegExp('[A-Za-z]{2,}');

/// The only strings allowed to hold letters: problem titles and slugs, the
/// submission language LeetCode reported and the ledger's path on the PC,
/// read from the fixture's own content fields. Nothing Claude wrote.
List<String> _content(String fixture) {
  final status =
      (jsonDecode(fixtureText(fixture)) as Map)['status'] as Map? ?? const {};
  final recent = (status['solves'] as Map?)?['recent'] as List? ?? const [];
  final suggestions = status['suggestions'] as List? ?? const [];
  return [
    for (final s in suggestions) ?(s as Map)['title'] as String?,
    for (final r in recent) ...[
      ?(r as Map)['title_slug'] as String?,
      ?r['lang'] as String?,
    ],
    ?(status['integrity'] as Map?)?['ledger_path'] as String?,
  ]..sort((a, b) => b.length.compareTo(a.length));
}

/// Every painted string under [root] that still holds a word once the
/// [content] is cut out. The projection section is included.
List<String> _words(
  WidgetTester tester,
  Finder root, [
  List<String> content = const [],
]) {
  final drawn = [
    for (final element
        in find
            .descendant(of: root, matching: find.byType(RichText))
            .evaluate())
      (element.widget as RichText).text.toPlainText(),
  ];
  // An empty tree would pass every check below: that is a broken pump.
  expect(drawn, isNotEmpty, reason: 'nothing painted under $root');
  return [
    for (final text in drawn)
      if (_word.hasMatch(content.fold(text, (t, c) => t.replaceAll(c, ''))))
        text,
  ];
}

void main() {
  for (final fixture in [
    'snapshot_full',
    'snapshot_real',
    'snapshot_stale',
    'snapshot_sparse',
    'snapshot_nulls',
  ]) {
    testWidgets('$fixture: the Status tab paints no words', (tester) async {
      await pumpApp(tester, answers: [fixture], size: const Size(390, 9000));
      final content = _content(fixture);
      final tab = find.byType(StatusTab);
      expect(tab, findsOneWidget);
      expect(_words(tester, tab, content), isEmpty);
      final buttons = [
        for (final e
            in find
                .byWidgetPredicate((w) => '${w.key}'.contains('show-all-'))
                .evaluate())
          e.widget.key!,
      ];
      // Why, pricing, environment and projection detail: sheets too.
      expect(find.byType(ProjectionSection), findsOneWidget);
      if (fixture == 'snapshot_full') {
        expect(buttons.length, greaterThanOrEqualTo(3));
      }
      for (final key in buttons) {
        await tester.tap(find.byKey(key));
        await tester.pumpAndSettle();
        final sheet = find.byType(BottomSheet);
        expect(_words(tester, sheet, content), isEmpty, reason: '$key');
        await tester.tapAt(const Offset(10, 10));
        await tester.pumpAndSettle();
      }
    });
  }

  for (final reason in [
    "Offline: can't reach Firebase",
    'Firebase answered HTTP 401',
    'Refresh failed (FormatException)',
  ]) {
    testWidgets('the stale banner paints no words: $reason', (tester) async {
      await pumpApp(
        tester,
        answers: [SnapshotUnavailable(reason)],
        size: const Size(390, 9000),
      );
      final banner = find.byKey(const Key('stale-banner'));
      expect(banner, findsOneWidget);
      expect(_words(tester, banner), isEmpty);
    });
  }
}

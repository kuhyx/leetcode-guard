// Guard for kuhy's textgate rule on the Post-mortem tab: before a tap it
// paints numbers, glyphs and one-word tooltips only; after a tap, only
// content (a unit or problem slug, a card front, the model's finding).
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/postmortem_chips.dart';
import 'package:leetcode_guard/src/ui/postmortem_grid.dart';
import 'package:leetcode_guard/src/ui/postmortem_tab.dart';
import 'package:material_ui/material_ui.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';
import '../support/text_scan.dart';

/// The one-word tooltips, as `paintedStrings` reports them.
final Set<String> _tooltips = {
  for (final (_, word) in kGridColumns) 'tooltip:$word',
  for (final (_, word) in kChangeGlyphs.values) 'tooltip:$word',
};

/// Every content string of the fixture's `postmortems` section.
Set<String> _content() {
  final json =
      jsonDecode(fixtureText('snapshot_postmortem')) as Map<String, Object?>;
  final out = <String>{};
  for (final unit in json['postmortems']! as List<Object?>) {
    final u = unit! as Map<String, Object?>;
    out.add(u['unit']! as String);
    for (final p in u['problems']! as List<Object?>) {
      final row = p! as Map<String, Object?>;
      out.addAll([row['slug']! as String, row['finding']! as String]);
    }
    for (final c in u['cards']! as List<Object?>) {
      final row = c! as Map<String, Object?>;
      out
        ..addAll([row['front']! as String, row['finding']! as String])
        ..addAll((row['used_by']! as List<Object?>).cast<String>());
    }
  }
  return out;
}

Finder get _tab => find.byType(PostmortemTab);

Future<void> _tap(WidgetTester tester, String k) async {
  await tester.ensureVisible(find.byKey(Key(k)));
  await tester.tap(find.byKey(Key(k)));
  await tester.pumpAndSettle();
}

void main() {
  for (final (name, size) in [
    ('phone', const Size(390, 4000)),
    ('desktop', kDesktop),
  ]) {
    testWidgets('$name: no words before a tap, only content after', (
      tester,
    ) async {
      await pumpApp(tester, answers: ['snapshot_postmortem'], size: size);
      await openTab(tester, kPostmortemTab);
      expectNoWords([_tab], _tooltips, where: '$name post-mortem');
      final content = _content();
      for (final k in ['pm-bar-1', 'pm-problem-7', 'pm-card-9']) {
        await _tap(tester, k);
      }
      expectNoWords([_tab], {..._tooltips, ...content}, where: '$name taps');
      expect(paintedStrings([_tab]), contains('prefix-sums'));
    });
  }

  testWidgets('phone pages paint no words', (tester) async {
    await pumpApp(tester, answers: ['snapshot_postmortem']);
    await openTab(tester, kPostmortemTab);
    expectNoWords([_tab], _tooltips, where: 'phone pages');
  });

  testWidgets('the empty state paints no words', (tester) async {
    final json =
        jsonDecode(fixtureText('snapshot_full')) as Map<String, Object?>;
    await pumpApp(
      tester,
      answers: [
        jsonEncode({...json, 'postmortems': <Object>[]}),
      ],
    );
    await openTab(tester, kPostmortemTab);
    expect(find.byKey(const Key('pm-empty')), findsOneWidget);
    expectNoWords([_tab], const {}, where: 'empty');
  });
}

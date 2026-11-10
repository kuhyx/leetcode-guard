// Guard for kuhy's textgate rule (2026-11-08): the shell, the Profile tab,
// the projection card and its "more" sheet paint no words.
//
// Scope: the app bar, the navigation bar/rail, `ProfileTab`, the
// `ProjectionSection` card and its sheet. The other Status cards and the
// Coach tab are reworked (and guarded) separately.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/profile_tab.dart';
import 'package:leetcode_guard/src/ui/projection_section.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';

/// A run of two or more ASCII letters: a word, or the start of one.
final _word = RegExp('[A-Za-z]{2,}');

/// Content these screens may paint verbatim. The full fixture puts no
/// username or problem title on them, so nothing is allowed.
const _content = <String>{};

/// Whether [e] is laid out but never painted: a hidden navigation label, a
/// zero-size box, an invisible or offstage subtree.
bool _hidden(Element e) {
  final box = e.renderObject;
  if (box is RenderBox && box.hasSize && box.size.isEmpty) return true;
  var hidden = false;
  e.visitAncestorElements((a) {
    hidden = switch (a.widget) {
      Opacity(:final opacity) => opacity == 0,
      FadeTransition(:final opacity) => opacity.value == 0,
      Visibility(:final visible) => !visible,
      Offstage(:final offstage) => offstage,
      _ => false,
    };
    return !hidden;
  });
  return hidden;
}

/// Every painted paragraph under [scope] (icons are one private-use glyph).
List<String> _painted(Finder scope) {
  final found = find
      .descendant(of: scope, matching: find.byType(RichText), matchRoot: true)
      .evaluate();
  return [
    for (final e in found)
      if (!_hidden(e)) (e.widget as RichText).text.toPlainText(),
  ];
}

/// Fails on any word under [scope]; an empty walk fails too, and [expected]
/// must be among the paragraphs so the walk provably reached the screen.
void _expectNoWords(Finder scope, String area, {String? expected}) {
  final painted = _painted(scope);
  expect(painted, isNotEmpty, reason: '$area: nothing painted was found');
  if (expected != null) expect(painted, contains(expected), reason: area);
  final words = [
    for (final t in painted)
      if (_word.hasMatch(t) && !_content.contains(t)) t,
  ];
  expect(words, isEmpty, reason: '$area paints words');
}

Future<void> _openProfile(WidgetTester tester) => openTab(tester, kProfileTab);

void main() {
  const tall = Size(390, 4000);

  testWidgets('phone: bar, nav, projection, its sheet, profile', (
    tester,
  ) async {
    await pumpApp(tester, size: tall);
    _expectNoWords(
      find.byType(AppBar),
      'app bar',
      expected: asOf(kGeneratedAt),
    );
    _expectNoWords(find.byType(NavigationBar), 'navigation bar');
    _expectNoWords(
      find.byType(ProjectionSection),
      'projection',
      expected: '312 / 4055',
    );
    await tester.tap(find.byKey(const Key('show-all-Progress & projection')));
    await tester.pumpAndSettle();
    _expectNoWords(
      find.byKey(const Key('sheet-Progress & projection')),
      'projection sheet',
    );
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    await _openProfile(tester);
    _expectNoWords(find.byType(ProfileTab), 'profile', expected: '120 / 900');
  });

  testWidgets('phone pages: profile chips and header', (tester) async {
    await pumpApp(tester);
    await _openProfile(tester);
    _expectNoWords(find.byType(ProfileTab), 'profile pages');
  });

  testWidgets('desktop: rail and profile', (tester) async {
    await pumpApp(tester, size: kDesktop);
    _expectNoWords(find.byType(NavigationRail), 'navigation rail');
    await _openProfile(tester);
    _expectNoWords(find.byType(ProfileTab), 'desktop profile');
  });

  testWidgets('profile unknown: no words either', (tester) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_nulls']);
    _expectNoWords(find.byType(ProjectionSection), 'unknown projection');
    await _openProfile(tester);
    _expectNoWords(
      find.byType(ProfileTab),
      'unknown profile',
      expected: kUnknown,
    );
  });
}

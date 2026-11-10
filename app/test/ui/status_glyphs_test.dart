// The Status tab's icon vocabulary: every value Python publishes has its
// own glyph, and anything unexpected falls back to a glyph, never a word.
import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/status_days.dart';
import 'package:leetcode_guard/src/ui/status_glyphs.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/status_sections.dart';

/// `GateState` values in `leetcode_guard/_gate_state.py` (2026-11-10).
const _gateStates = [
  'not-started',
  'already-charged',
  'charged',
  'locked',
  'locked-clock',
  'free-day',
  'sick-day',
  'focus-day',
];

void main() {
  test('each gate state has its own icon; others are a question', () {
    final icons = {for (final s in _gateStates) gateStateIcon(s)};
    expect(icons, hasLength(_gateStates.length));
    expect(icons, isNot(contains(Icons.help_outline)));
    expect(gateStateIcon('settled'), Icons.help_outline);
    expect(gateStateIcon(null), Icons.help_outline);
  });

  test('pool sources: live, cache, stale cache, none, unknown', () {
    expect(poolSourceIcon('live'), (Icons.cloud_done_outlined, false));
    expect(poolSourceIcon('live pool (4003 problems)').$1, isNot(Icons.help));
    expect(poolSourceIcon('cache'), (Icons.save_outlined, false));
    expect(poolSourceIcon('stale-cache'), (Icons.history, true));
    expect(poolSourceIcon('none'), (Icons.cloud_off, true));
    expect(poolSourceIcon('elsewhere'), (Icons.help_outline, false));
    expect(poolSourceIcon(null), (Icons.help_outline, false));
  });

  test('budgets: an icon each, counts per window, else plain numbers', () {
    expect(budgetIcon('escape'), isNot(budgetIcon('incidents')));
    expect(budgetIcon('other'), Icons.savings_outlined);
    final real = Budget.fromJson(const {
      'used_7': 0,
      'limit_7': 1,
      'used_30': 0,
      'limit_30': 3,
    });
    expect(budgetCounts(real), '0 / 1 (7d)   0 / 3 (30d)');
    expect(
      budgetCounts(Budget.fromJson(const {'limit_90': 10})),
      '? / 10 (90d)',
    );
    expect(budgetCounts(Budget.fromJson(const {'used': 1, 'x': 2})), '1 · 2');
  });

  test('a sentence is reduced to its dates and numbers', () {
    expect(factsOf('cookie valid until 2026-11-02'), '2026-11-02');
    expect(factsOf('Sat 2026-10-24 09:00:00 CEST'), '2026-10-24 09:00:00');
    expect(factsOf('4087 entries, 2.2 days old, 52.0%'), '4087 · 2.2 · 52.0%');
    expect(factsOf('statement cache warm'), '');
  });

  testWidgets('difficulty: bars and colour by level', (tester) async {
    late List<(IconData, Color?)> glyphs;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildDarkTheme(),
        home: Builder(
          builder: (context) {
            glyphs = [
              for (final level in ['Easy', 'Medium', 'Hard', 'Odd', null])
                difficultyGlyph(context, level),
            ];
            return const SizedBox();
          },
        ),
      ),
    );
    expect({for (final g in glyphs.take(3)) g.$1}, hasLength(3));
    expect(glyphs[3], (Icons.help_outline, null));
    expect(glyphs[4], (Icons.help_outline, null));
  });

  test('section icons are keyed by their spoken title', () {
    final icon = sectionIcon(Icons.toll, 'Credits (tokens)');
    expect(icon.semanticLabel, 'Credits (tokens)');
    expect(icon.key, const Key('section-credits-tokens'));
  });
}

// The live post-mortem card: stage glyphs, a bar over the tutor's estimate,
// elapsed time and the ETA, an overrun, and how the last run ended.
import 'dart:convert';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/postmortem_progress.dart';
import 'package:leetcode_guard/src/ui/postmortem_tab.dart';
import 'package:material_ui/material_ui.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';
import '../support/text_scan.dart';

/// 2026-11-28 19:56:00 UTC, the run's start.
const kStart = 1795895760.0;
final DateTime kStartAt = DateTime.fromMillisecondsSinceEpoch(
  (kStart * 1000).round(),
  isUtc: true,
);

Map<String, Object?> running({Object? stage = 'analysing'}) => {
  'state': 'running',
  'unit': 'prefix-sums',
  'rev': 1,
  'stage': stage,
  'started_at': kStart,
  'stage_at': kStart,
  'finished_at': null,
  'estimate_s': 600.0,
  'summary': null,
  'error': null,
};

PostmortemProgress parse(Map<String, Object?> json) =>
    PostmortemProgress.fromJson(json);

Finder key(String k) => find.byKey(Key(k));

String textOf(WidgetTester tester, String k) =>
    tester.widget<Text>(key(k)).data!;

Color? iconColour(WidgetTester tester, String k) =>
    tester.widget<Icon>(key(k)).color;

double? barValue(WidgetTester tester) =>
    tester.widget<LinearProgressIndicator>(key('pm-progress-bar')).value;

/// Pumps the tab alone over [progress] at a mutable clock.
Future<void Function(Duration)> pumpTab(
  WidgetTester tester,
  Map<String, Object?>? progress, {
  Duration after = const Duration(minutes: 4),
  List<PostmortemUnit>? units = const [],
}) async {
  var now = kStartAt.add(after);
  tester.view.physicalSize = const Size(390, 4000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: PostmortemTab(
          units: units,
          progress: progress == null ? null : parse(progress),
          now: () => now,
        ),
      ),
    ),
  );
  await tester.pump();
  return (d) => now = now.add(d);
}

void main() {
  test('the model parses times, the estimate and the ETA', () {
    final p = parse(running());
    expect(p.state, PostmortemState.running);
    expect(p.stage, PostmortemStage.analysing);
    expect(p.startedAt, kStartAt);
    expect(p.estimate, const Duration(minutes: 10));
    expect(p.eta, kStartAt.add(const Duration(minutes: 10)));
    final blank = parse(const {'state': 'paused', 'stage': 'x'});
    expect(blank.state, isNull);
    expect(blank.stage, isNull);
    expect(blank.eta, isNull);
    expect(blank.unit, '');
  });

  test('a running or failed run shows; a done one for six hours', () {
    final now = kStartAt.add(const Duration(hours: 1));
    expect(showProgress(null, now), isFalse);
    expect(showProgress(parse(running()), now), isTrue);
    expect(showProgress(parse(const {'state': 'failed'}), now), isTrue);
    expect(showProgress(parse(const {'state': 'done'}), now), isFalse);
    final done = parse({...running(), 'state': 'done', 'finished_at': kStart});
    expect(showProgress(done, now), isTrue);
    expect(showProgress(done, now.add(kShowDoneFor)), isFalse);
    expect(showProgress(parse(const {'state': 'nope'}), now), isFalse);
  });

  test('clockOf reads minutes and hours, never negative', () {
    expect(clockOf(const Duration(seconds: 65)), '1:05');
    expect(
      clockOf(const Duration(hours: 1, minutes: 2, seconds: 3)),
      '1:02:03',
    );
    expect(clockOf(const Duration(seconds: -5)), '0:00');
  });

  testWidgets('running: stage lit, bar at elapsed/estimate, ETA, live tick', (
    tester,
  ) async {
    final advance = await pumpTab(tester, running(stage: 'applying'));
    expect(key('pm-progress'), findsOneWidget);
    expect(iconColour(tester, 'pm-stage-analysing'), AppPalette.success);
    expect(iconColour(tester, 'pm-stage-applying'), AppPalette.accent);
    expect(iconColour(tester, 'pm-stage-saving'), isNot(AppPalette.accent));
    expect(barValue(tester), closeTo(0.4, 1e-9));
    expect(textOf(tester, 'pm-progress-elapsed'), '$kElapsed 4:00');
    expect(
      textOf(tester, 'pm-progress-eta'),
      asOfLocal(kStartAt.add(const Duration(minutes: 10))),
    );
    expect(key('pm-progress-over'), findsNothing);
    advance(const Duration(seconds: 30));
    await tester.pump(const Duration(seconds: 1));
    expect(textOf(tester, 'pm-progress-elapsed'), '$kElapsed 4:30');
    advance(const Duration(minutes: 7));
    await tester.pump(const Duration(seconds: 1));
    expect(textOf(tester, 'pm-progress-over'), '+1:30');
    expect(barValue(tester), 0.99); // held short of full until it really ends
  });

  testWidgets('an unknown start or estimate is an indeterminate bar', (
    tester,
  ) async {
    await pumpTab(tester, {
      ...running(),
      'estimate_s': null,
      'started_at': null,
    });
    expect(barValue(tester), isNull);
    expect(textOf(tester, 'pm-progress-elapsed'), '$kElapsed ?');
    expect(textOf(tester, 'pm-progress-eta'), '◷ ?');
  });

  testWidgets('done: full bar, the run time, the end and the summary', (
    tester,
  ) async {
    await pumpTab(tester, {
      ...running(stage: null),
      'state': 'done',
      'finished_at': kStart + 630,
      'summary': {'added': 9, 'edited': 6, 'untaught': 6, 'suspended': 2},
    });
    expect(barValue(tester), 1.0);
    expect(textOf(tester, 'pm-progress-elapsed'), '$kElapsed 10:30');
    expect(
      textOf(tester, 'pm-progress-eta'),
      asOfLocal(kStartAt.add(const Duration(seconds: 630))),
    );
    expect(textOf(tester, 'pm-progress-added'), '9');
    expect(textOf(tester, 'pm-progress-suspended'), '2');
    expect(iconColour(tester, 'pm-stage-saving'), AppPalette.success);
  });

  testWidgets('failed: a danger bar and the error behind a tap', (
    tester,
  ) async {
    await pumpTab(tester, {
      ...running(stage: null),
      'state': 'failed',
      'finished_at': kStart + 60,
      'error': 'claude unavailable',
    });
    expect(
      tester.widget<LinearProgressIndicator>(key('pm-progress-bar')).color,
      AppPalette.danger,
    );
    expect(find.text('claude unavailable'), findsNothing);
    await tester.tap(key('pm-progress-tap'));
    await tester.pump();
    expect(find.text('prefix-sums'), findsOneWidget);
    expect(find.text('claude unavailable'), findsOneWidget);
    await tester.tap(key('pm-progress-tap'));
    await tester.pump();
    expect(key('pm-progress-reveal'), findsNothing);
  });

  testWidgets('no progress: the empty tab keeps its glyph', (tester) async {
    await pumpTab(tester, null);
    expect(key('pm-progress'), findsNothing);
    expect(key('pm-empty'), findsOneWidget);
  });

  testWidgets('unknown units: the card sits above the unknown sections', (
    tester,
  ) async {
    await pumpTab(tester, running(), units: null);
    expect(key('pm-progress'), findsOneWidget);
    expect(key('pm-section-chart'), findsOneWidget);
  });

  testWidgets('the tick stops once the run is over', (tester) async {
    await pumpTab(tester, running());
    await pumpTab(tester, {
      ...running(),
      'state': 'done',
      'finished_at': kStart,
    });
    expect(tester.binding.transientCallbackCount, 0);
    await tester.pump(const Duration(seconds: 5)); // no pending timer left
  });

  for (final (name, size) in [
    ('phone', const Size(390, 4000)),
    ('desktop', kDesktop),
  ]) {
    testWidgets('$name: the snapshot drives the card, and it paints no words', (
      tester,
    ) async {
      final json = jsonDecode(
        fixtureText('snapshot_postmortem'),
      ) as Map<String, Object?>;
      final start =
          kGeneratedAt.add(const Duration(minutes: -3)).millisecondsSinceEpoch /
          1000;
      final body = jsonEncode({
        ...json,
        'postmortem_progress': {...running(), 'started_at': start},
      });
      await pumpApp(tester, answers: [body], size: size);
      await openTab(tester, kPostmortemTab);
      expect(key('pm-progress'), findsOneWidget);
      expect(textOf(tester, 'pm-progress-elapsed'), '$kElapsed 4:00');
      expectNoWords(
        [find.byKey(const Key('pm-progress'))],
        {for (final (_, w) in kStageGlyphs.values) 'tooltip:$w'},
        where: '$name progress card',
      );
    });
  }
}

/// [asOf] of a UTC instant, as the card renders it (device local time).
String asOfLocal(DateTime at) {
  final t = at.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '◷ ${two(t.hour)}:${two(t.minute)}';
}

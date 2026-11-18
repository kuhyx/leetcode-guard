// The app's hooks into the shared app-errors reporter (kuhyx/utils
// DOCS-app-errors.md): the first-load wait is timed, routes are named.
import 'dart:async';

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

const _config = AppErrorsConfig(
  app: 'leetcode-guard-app',
  repo: 'kuhyx/leetcode-guard',
  package: 'leetcode_guard',
  build: 7,
);

/// A source whose first fetch waits for [gate].
class _GatedSource implements SnapshotSource {
  new(this.gate, this.answer);

  final Completer<void> gate;
  final Object answer;

  @override
  Future<String?> fetch() async {
    await gate.future;
    final a = answer;
    if (a is Exception) throw a;
    return a as String;
  }

  @override
  Future<String?> heartbeat() async => null;
}

void main() {
  late DateTime clock;
  late AppErrors errors;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    clock = DateTime.utc(2026, 11, 18, 20);
    final queue = await ErrorQueue.open(await SharedPreferences.getInstance());
    errors = AppErrors.instance = AppErrors.forTest(
      _config,
      queue,
      now: () => clock,
    );
  });

  tearDown(() => AppErrors.instance = null);

  Future<Completer<void>> pumpGated(WidgetTester tester, Object answer) async {
    final gate = Completer<void>();
    final controller = StatusController(
      source: _GatedSource(gate, answer),
      cache: MemoryCache(),
      clock: clockAfter(1),
    );
    await tester.pumpWidget(
      LeetGuardApp(
        controller: controller,
        openUrl: (_) async => true,
        errors: errors,
        settingsBuilder: (_) => const Scaffold(body: SizedBox()),
      ),
    );
    await tester.pump();
    return gate;
  }

  List<ErrorEntry> slow() =>
      [for (final e in errors.queue.entries) if (e.kind == 'perf.slow') e];

  testWidgets('a first load over 1 s files one perf.slow', (
    tester,
  ) async {
    final gate = await pumpGated(tester, fixtureText('snapshot_full'));
    clock = clock.add(const Duration(seconds: 2));
    gate.complete();
    await tester.pumpAndSettle();
    final waits = slow();
    expect(waits, hasLength(1));
    expect(waits.single.operation, 'snapshot.load');
  });

  testWidgets('a quick first load files nothing', (tester) async {
    final gate = await pumpGated(tester, fixtureText('snapshot_full'));
    clock = clock.add(const Duration(milliseconds: 300));
    gate.complete();
    await tester.pumpAndSettle();
    expect(slow(), isEmpty);
  });

  testWidgets('a failed load ends the wait: offline is not timed forever', (
    tester,
  ) async {
    final gate = await pumpGated(tester, const SnapshotUnavailable('offline'));
    gate.complete();
    await tester.pumpAndSettle();
    clock = clock.add(const Duration(minutes: 5));
    await tester.pump();
    expect(slow(), isEmpty);
  });

  testWidgets('opening settings stamps a named route', (tester) async {
    final gate = await pumpGated(tester, fixtureText('snapshot_full'));
    gate.complete();
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Sync account'));
    await tester.pumpAndSettle();
    expect(errors.reporter.route, '/settings');
  });
}

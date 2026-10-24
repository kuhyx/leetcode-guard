import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

const _token = 'eyJhbGciOiJSUzI1NiJ9.SECRETPAYLOAD.SIGNATURE';

/// The Pixel 6a in portrait (logical pixels).
const _pixel6a = Size(412, 915);

/// Every string drawn on screen.
Iterable<String> _drawn(WidgetTester tester) => tester
    .widgetList<RichText>(find.byType(RichText))
    .map((r) => r.text.toPlainText());

Text _bannerText(WidgetTester tester) => tester.widget<Text>(
  find.descendant(
    of: find.byKey(const Key('stale-banner')),
    matching: find.byType(Text),
  ),
);

Future<StatusController> _pump(
  WidgetTester tester,
  SnapshotSource source, {
  Size size = _pixel6a,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final controller = StatusController(
    source: source,
    cache: MemoryCache(fixtureText('snapshot_full')),
    clock: clockAfter(2),
  );
  await tester.pumpWidget(
    LeetGuardApp(controller: controller, openUrl: (_) async => true),
  );
  await tester.pumpAndSettle();
  return controller;
}

InMemoryCredentialStore _signedIn() {
  final store = InMemoryCredentialStore();
  unawaited(
    store.save(
      FirebaseCredentials(
        idToken: _token,
        refreshToken: 'r',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      ),
    ),
  );
  return store;
}

void main() {
  testWidgets('the 2026-10-24 DNS failure: short, bounded, no token', (
    tester,
  ) async {
    // The real source over a client failing the way the phone did, so the
    // URL with `?auth=<token>` is in the exception, as it was that day.
    final source = FirebaseSnapshotSource(
      open: () async => FirebaseRestClient(
        databaseUrl: 'https://db.example',
        auth: FirebaseTokenProvider(apiKey: 'k', store: _signedIn()),
      ),
      databaseUrl:
          'https://kuhy-syncs-default-rtdb.europe-west1'
          '.firebasedatabase.app',
      httpClient: MockClient(
        (r) async => throw http.ClientException(
          "SocketException: Failed host lookup: '${r.url.host}' (OS Error: "
          'No address associated with hostname, errno = 7)',
          r.url,
        ),
      ),
    );
    await _pump(tester, source);
    expect(find.byKey(const Key('stale-banner')), findsOneWidget);
    for (final expanded in [false, true]) {
      final drawn = _drawn(tester).join('\n');
      expect(drawn, contains("Offline: can't reach Firebase"));
      for (final secret in ['SECRETPAYLOAD', 'auth=', '?', 'http']) {
        expect(drawn, isNot(contains(secret)), reason: 'expanded: $expanded');
      }
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const Key('stale-banner')));
      await tester.pumpAndSettle();
    }
  });

  testWidgets('a long error is two lines; a tap shows it all, still bounded', (
    tester,
  ) async {
    final long = List.filled(400, 'word').join(' ');
    await _pump(
      tester,
      FakeSource([SnapshotUnavailable(long)]),
      size: const Size(320, 640),
    );
    final collapsed = _bannerText(tester);
    expect(collapsed.maxLines, 2);
    expect(collapsed.overflow, TextOverflow.ellipsis);
    final twoLines = tester.getSize(find.byKey(const Key('stale-banner')));
    expect(twoLines.height, lessThan(80));
    expect(tester.takeException(), isNull);

    await tester.tap(find.byKey(const Key('stale-banner')));
    await tester.pumpAndSettle();
    expect(_bannerText(tester).maxLines, isNull);
    final open = tester.getSize(find.byKey(const Key('stale-banner')));
    expect(open.height, greaterThan(twoLines.height));
    expect(open.height, lessThanOrEqualTo(640 / 2));
    expect(tester.takeException(), isNull);

    await tester.tap(find.byKey(const Key('stale-banner')));
    await tester.pumpAndSettle();
    expect(_bannerText(tester).maxLines, 2);
  });
}

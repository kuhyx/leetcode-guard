import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';
import 'package:leetcode_guard/src/ui/stale_banner.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

const _token = 'eyJhbGciOiJSUzI1NiJ9.SECRETPAYLOAD.SIGNATURE';

/// The Pixel 6a in portrait (logical pixels).
const _pixel6a = Size(412, 915);

/// Every string drawn in the banner.
Iterable<String> _drawn(WidgetTester tester) => tester
    .widgetList<RichText>(
      find.descendant(
        of: find.byKey(const Key('stale-banner')),
        matching: find.byType(RichText),
      ),
    )
    .map((r) => r.text.toPlainText());

/// What the banner says to a screen reader.
String _spoken(WidgetTester tester) =>
    tester.widget<StaleBanner>(find.byType(StaleBanner)).spoken;

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
    final semantics = tester.ensureSemantics();
    await _pump(tester, source);
    expect(find.byKey(const Key('stale-banner')), findsOneWidget);
    // Painted: the age and the offline cloud, no words, no secret.
    expect(find.byKey(const Key('failure-offline')), findsOneWidget);
    expect(find.byKey(const Key('stale-age')), findsOneWidget);
    final drawn = _drawn(tester).join('\n');
    expect(drawn, isNot(matches(RegExp('[A-Za-z]{2,}'))));
    // Spoken: the reason, and still no secret in the accessibility tree.
    final spoken = _spoken(tester);
    expect(spoken, contains("Offline: can't reach Firebase"));
    expect(
      find.bySemanticsLabel(RegExp("Offline: can't reach Firebase")),
      findsOneWidget,
    );
    for (final secret in ['SECRETPAYLOAD', 'auth=', '?', 'http']) {
      expect(drawn, isNot(contains(secret)));
      expect(spoken, isNot(contains(secret)));
    }
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets('a long error stays one bounded strip; all of it is spoken', (
    tester,
  ) async {
    final long = List.filled(400, 'word').join(' ');
    await _pump(
      tester,
      FakeSource([SnapshotUnavailable(long)]),
      size: const Size(320, 640),
    );
    final strip = tester.getSize(find.byKey(const Key('stale-banner')));
    expect(strip.height, lessThan(80));
    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('failure-other')), findsOneWidget);
    expect(_spoken(tester), endsWith(long));
  });

  testWidgets('an HTTP failure paints its status code', (tester) async {
    await _pump(tester, FakeSource([SnapshotUnavailable(httpFailure(503))]));
    expect(find.byKey(const Key('failure-http')), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const Key('stale-banner')),
        matching: find.text('503'),
      ),
      findsOneWidget,
    );
  });

  test('each failure the sources produce has its own kind', () {
    expect(failureKind(kOfflineText), FailureKind.offline);
    expect(failureKind(kTimeoutText), FailureKind.timeout);
    expect(failureKind(httpFailure(401)), FailureKind.http);
    expect(failureKind('Wrapper HTTP 500: oops'), FailureKind.http);
    expect(httpStatusIn('Wrapper HTTP 500: oops'), 500);
    expect(httpStatusIn('network down'), isNull);
    expect(
      failureKind(describeSignInFailure(const FormatException('x'))),
      FailureKind.signIn,
    );
    expect(failureKind('network down'), FailureKind.other);
    for (final kind in FailureKind.values) {
      expect(failureIcon(kind), isA<IconData>());
    }
    expect({
      for (final kind in FailureKind.values) failureIcon(kind),
    }, hasLength(FailureKind.values.length));
  });
}

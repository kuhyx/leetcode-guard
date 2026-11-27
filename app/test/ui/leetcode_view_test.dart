// The in-app LeetCode view: the one way to open a problem on a phone with
// no browser at home (kuhy, 2026-11-27). It loads leetcode.com only.
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/leetcode_view.dart';
import 'package:leetcode_guard/src/ui/problem_opener.dart';
import 'package:material_ui/material_ui.dart';
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

import '../support/fake_webview.dart';
import '../support/text_scan.dart';

final Uri _problem = Uri.parse('https://leetcode.com/problems/two-sum/');

/// A bare app whose navigator [key] the opener pushes onto.
Future<void> _pumpHost(WidgetTester tester, GlobalKey<NavigatorState> key) =>
    tester.pumpWidget(
      MaterialApp(
        navigatorKey: key,
        home: const Scaffold(body: SizedBox.expand(key: Key('host'))),
      ),
    );

void main() {
  group('isLeetcodePage', () {
    test('admits https pages of leetcode.com and its subdomains', () {
      for (final url in [
        'https://leetcode.com/problems/two-sum/',
        'https://leetcode.com/accounts/login/',
        'https://assets.leetcode.com/x.js',
        'https://leetcode.com',
      ]) {
        expect(isLeetcodePage(url), isTrue, reason: url);
      }
    });

    test('refuses every other page', () {
      for (final url in [
        'http://leetcode.com/problems/two-sum/',
        'https://leetcode.com.evil.example/',
        'https://evilleetcode.com/',
        'https://user@leetcode.com/',
        'https://leetcode.com:8443/',
        'https://www.google.com/search?q=leetcode',
        'leetcode://problems/two-sum',
        'intent://leetcode.com#Intent;end',
        'javascript:alert(1)',
        'about:blank',
        '',
      ]) {
        expect(isLeetcodePage(url), isFalse, reason: url);
      }
    });
  });

  testWidgets('a problem link opens the view on that page, JS on', (
    tester,
  ) async {
    final web = installFakeWebView();
    final key = GlobalKey<NavigatorState>();
    final fallback = <Uri>[];
    await _pumpHost(tester, key);
    final opener = InAppProblemOpener(
      navigator: key,
      fallback: (uri) async {
        fallback.add(uri);
        return true;
      },
    );
    expect(await opener(_problem), isTrue);
    await tester.pumpAndSettle();
    expect(find.byType(LeetcodeView), findsOneWidget);
    expect(web.controller.loaded, [_problem]);
    expect(web.controller.javaScript, JavaScriptMode.unrestricted);
    expect(fallback, isEmpty);
    expectNoWords([find.byType(LeetcodeView)], {}, where: 'leetcode view');
  });

  testWidgets('anything but a problem page goes to the fallback', (
    tester,
  ) async {
    installFakeWebView();
    final key = GlobalKey<NavigatorState>();
    final fallback = <Uri>[];
    await _pumpHost(tester, key);
    final opener = InAppProblemOpener(
      navigator: key,
      fallback: (uri) async {
        fallback.add(uri);
        return false;
      },
    );
    final tutor = Uri.parse('kuhytutor://review/s/m');
    expect(await opener(tutor), isFalse);
    await tester.pumpAndSettle();
    expect(fallback, [tutor]);
    expect(find.byType(LeetcodeView), findsNothing);
  });

  test('no navigator yet is a false, not a crash', () async {
    final opener = InAppProblemOpener(
      navigator: GlobalKey<NavigatorState>(),
      fallback: (_) async => true,
    );
    expect(await opener(_problem), isFalse);
  });

  testWidgets('only leetcode.com loads in the main frame; frames are free', (
    tester,
  ) async {
    final web = installFakeWebView();
    await tester.pumpWidget(MaterialApp(home: LeetcodeView(url: _problem)));
    final d = web.delegate;
    expect(
      await d.decide('https://leetcode.com/problems/add-two-numbers/'),
      NavigationDecision.navigate,
    );
    expect(
      await d.decide('https://www.google.com/'),
      NavigationDecision.prevent,
    );
    expect(
      await d.decide('leetcode://problems/two-sum'),
      NavigationDecision.prevent,
    );
    // Cloudflare's check and payment widgets live in iframes.
    expect(
      await d.decide('https://challenges.cloudflare.com/x', mainFrame: false),
      NavigationDecision.navigate,
    );
  });

  testWidgets('a progress bar shows while loading, then goes', (tester) async {
    final web = installFakeWebView();
    await tester.pumpWidget(MaterialApp(home: LeetcodeView(url: _problem)));
    web.delegate.progress(40);
    await tester.pump();
    final bar = tester.widget<LinearProgressIndicator>(
      find.byType(LinearProgressIndicator),
    );
    expect(bar.value, closeTo(0.4, 1e-9));
    web.delegate.progress(100);
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  testWidgets('back walks the page history first, then leaves', (tester) async {
    final web = installFakeWebView();
    final key = GlobalKey<NavigatorState>();
    await _pumpHost(tester, key);
    await InAppProblemOpener(navigator: key, fallback: (_) async => true)(
      _problem,
    );
    await tester.pumpAndSettle();
    web.controller.history = 1;
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(web.controller.wentBack, 1);
    expect(find.byType(LeetcodeView), findsOneWidget);
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(LeetcodeView), findsNothing);
  });

  testWidgets('the close button leaves at once', (tester) async {
    final web = installFakeWebView();
    final key = GlobalKey<NavigatorState>();
    await _pumpHost(tester, key);
    await InAppProblemOpener(navigator: key, fallback: (_) async => true)(
      _problem,
    );
    await tester.pumpAndSettle();
    web.controller.history = 3;
    await tester.tap(find.byKey(kLeetcodeCloseKey));
    await tester.pumpAndSettle();
    expect(find.byType(LeetcodeView), findsNothing);
    expect(web.controller.wentBack, 0);
  });
}

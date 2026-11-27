/// Where a tap on a LeetCode problem goes on the phone: the in-app
/// [LeetcodeView]. Every other link (the tutor) keeps the OS opener.
library;

import 'package:leetcode_guard/src/problem_url.dart';
import 'package:leetcode_guard/src/ui/leetcode_view.dart';
import 'package:leetcode_guard/src/ui/status_suggestions.dart';
import 'package:material_ui/material_ui.dart';

/// A [UrlOpener] that pushes [LeetcodeView] for a problem page.
class InAppProblemOpener {
  /// Opens problems over [navigator], anything else through [fallback].
  const new({required this.navigator, required this.fallback});

  /// The app's navigator (MaterialApp.navigatorKey).
  final GlobalKey<NavigatorState> navigator;

  /// The opener for every link that is not a problem page.
  final UrlOpener fallback;

  /// Opens [uri]; false when nothing could (no navigator yet, or the
  /// fallback refused).
  Future<bool> call(Uri uri) async {
    if (!isProblemUrl(uri.toString())) return await fallback(uri);
    final nav = navigator.currentState;
    if (nav == null) return false;
    nav.push(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/leetcode'),
        builder: (_) => LeetcodeView(url: uri),
      ),
    );
    return true;
  }
}

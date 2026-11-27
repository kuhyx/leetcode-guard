// A WebView platform that records what the app asks of it, so the LeetCode
// view runs under flutter_test (which has no real WebView).
import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

/// Installs a fresh [FakeWebViewPlatform]; returns it. The platform slot
/// refuses null, so nothing is restored: every test installs its own.
FakeWebViewPlatform installFakeWebView() {
  final fake = FakeWebViewPlatform();
  WebViewPlatform.instance = fake;
  return fake;
}

/// The fake platform: the last controller and delegate it created.
class FakeWebViewPlatform extends WebViewPlatform {
  /// The controller the view created.
  late FakeWebController controller;

  /// The delegate the view created.
  late FakeNavigationDelegate delegate;

  @override
  PlatformWebViewController createPlatformWebViewController(
    PlatformWebViewControllerCreationParams params,
  ) => controller = FakeWebController(params);

  @override
  PlatformNavigationDelegate createPlatformNavigationDelegate(
    PlatformNavigationDelegateCreationParams params,
  ) => delegate = FakeNavigationDelegate(params);

  @override
  PlatformWebViewWidget createPlatformWebViewWidget(
    PlatformWebViewWidgetCreationParams params,
  ) => _FakeWebWidget(params);
}

/// Records loads and the JavaScript mode; [history] drives back.
class FakeWebController extends PlatformWebViewController {
  /// Creates the controller.
  new(super.params) : super.implementation();

  /// Every URL loaded, in order.
  final loaded = <Uri>[];

  /// The JavaScript mode last set.
  JavaScriptMode? javaScript;

  /// Pages behind the current one; `goBack` pops one.
  int history = 0;

  /// How many times `goBack` ran.
  int wentBack = 0;

  @override
  Future<void> loadRequest(LoadRequestParams params) async =>
      loaded.add(params.uri);

  @override
  Future<void> setJavaScriptMode(JavaScriptMode javaScriptMode) async =>
      javaScript = javaScriptMode;

  @override
  Future<void> setPlatformNavigationDelegate(
    PlatformNavigationDelegate handler,
  ) async {}

  @override
  Future<bool> canGoBack() async => history > 0;

  @override
  Future<void> goBack() async {
    history--;
    wentBack++;
  }
}

/// Keeps the callbacks so a test can play the page's side.
class FakeNavigationDelegate extends PlatformNavigationDelegate {
  /// Creates the delegate.
  new(super.params) : super.implementation();

  late NavigationRequestCallback _onRequest;
  late ProgressCallback _onProgress;

  /// What the view decides for a navigation to [url].
  Future<NavigationDecision> decide(
    String url, {
    bool mainFrame = true,
  }) async =>
      await _onRequest(NavigationRequest(url: url, isMainFrame: mainFrame));

  /// The page reports [percent] loaded.
  void progress(int percent) => _onProgress(percent);

  @override
  Future<void> setOnNavigationRequest(
    NavigationRequestCallback onNavigationRequest,
  ) async => _onRequest = onNavigationRequest;

  @override
  Future<void> setOnProgress(ProgressCallback onProgress) async =>
      _onProgress = onProgress;
}

class _FakeWebWidget extends PlatformWebViewWidget {
  new(super.params) : super.implementation();

  @override
  Widget build(BuildContext context) =>
      const SizedBox.expand(key: Key('fake-webview'));
}

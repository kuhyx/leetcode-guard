/// A LeetCode problem inside this app (kuhy, 2026-11-27). At home the phone
/// has no browser, and the LeetCode app stops at its PairIP licence check
/// because the focus policy hides Play, so this view is how a lock row opens
/// a problem. It is no general browser: the page itself may only move to
/// https pages of leetcode.com and its subdomains.
///
/// No words (textgate): a close glyph and a progress bar.
library;

import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Key of the button that closes the view.
const kLeetcodeCloseKey = Key('leetcode-close');

/// Whether the page may navigate to [url]: https on `leetcode.com` or one of
/// its subdomains, on the default port, with no user info.
bool isLeetcodePage(String url) {
  final uri = Uri.tryParse(url);
  if (uri == null || uri.scheme != 'https') return false;
  if (uri.userInfo.isNotEmpty || uri.hasPort) return false;
  return uri.host == 'leetcode.com' || uri.host.endsWith('.leetcode.com');
}

/// The page at [url], full screen, with a close button.
class LeetcodeView extends StatefulWidget {
  /// Creates the view on [url].
  const new({required this.url, super.key});

  /// The problem page it opens on.
  final Uri url;

  @override
  State<LeetcodeView> createState() => _LeetcodeViewState();
}

class _LeetcodeViewState extends State<LeetcodeView> {
  final _web = WebViewController();
  int _progress = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_open());
  }

  Future<void> _open() async {
    await _web.setJavaScriptMode(JavaScriptMode.unrestricted);
    await _web.setNavigationDelegate(
      NavigationDelegate(
        // Frames (Cloudflare's check, payment widgets) load freely; only the
        // page itself is held to leetcode.com.
        onNavigationRequest: (request) =>
            !request.isMainFrame || isLeetcodePage(request.url)
            ? NavigationDecision.navigate
            : NavigationDecision.prevent,
        onProgress: (percent) {
          if (mounted) setState(() => _progress = percent);
        },
      ),
    );
    await _web.loadRequest(widget.url);
  }

  /// System back: a page back inside LeetCode first, then out of the view.
  Future<void> _back() async {
    if (await _web.canGoBack()) {
      await _web.goBack();
      return;
    }
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    onPopInvokedWithResult: (didPop, _) {
      if (!didPop) unawaited(_back());
    },
    child: Scaffold(
      appBar: AppBar(
        leading: IconButton(
          key: kLeetcodeCloseKey,
          icon: const Icon(Icons.close, semanticLabel: 'Close'),
          onPressed: () => Navigator.of(context).pop(),
        ),
        bottom: _progress < 100
            ? PreferredSize(
                preferredSize: const Size.fromHeight(2),
                child: LinearProgressIndicator(value: _progress / 100),
              )
            : null,
      ),
      body: WebViewWidget(controller: _web),
    ),
  );
}

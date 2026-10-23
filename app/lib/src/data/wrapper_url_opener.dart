/// The desktop's suggestion links: asked of the wrapper, never opened here.
///
/// The app window runs with every hostname but loopback unresolvable (see
/// `browserArgs`), so a link opened in it would fail, and a window that
/// could reach the web would be an unfiltered browser. The wrapper hands
/// the URL to `xdg-open` instead, which lands in kuhy's normal, filtered one.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

/// Wrapper route that opens a problem page in the system browser.
const kOpenPath = '/open';

/// Opens a URL by POSTing it to the wrapper at [base].
class WrapperUrlOpener {
  /// Creates an opener for the wrapper origin [base].
  new({required this.base, http.Client? client})
    : _client = client ?? http.Client();

  /// The page's own origin.
  final Uri base;
  final http.Client _client;

  /// Asks the wrapper to open [uri]; true when it did. The wrapper refuses
  /// anything but a LeetCode problem page.
  Future<bool> call(Uri uri) async {
    try {
      final res = await _client.post(
        base.resolve(kOpenPath),
        headers: {'content-type': 'application/json'},
        body: jsonEncode({'url': uri.toString()}),
      );
      return res.statusCode == 204;
    } on http.ClientException {
      return false;
    }
  }
}

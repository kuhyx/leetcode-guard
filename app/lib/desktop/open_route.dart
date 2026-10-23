/// `POST /open`: the wrapper opens a suggestion in kuhy's own browser.
///
/// The app window cannot resolve anything but loopback (`browserArgs`), so
/// it asks the wrapper, which runs `xdg-open` and lands the page in the
/// normal, filtered browser. Only `isProblemUrl` URLs pass: this endpoint is
/// reachable by any local process, so it must not be a generic launcher.
library;

import 'dart:convert';
import 'dart:io';

import 'package:leetcode_guard/src/problem_url.dart';

/// Opens [url] outside the app window.
typedef UrlLauncher = Future<void> Function(String url);

/// Starts a detached process; [Process.start] in production.
typedef DetachedStarter = Future<Process> Function(
  String executable,
  List<String> arguments, {
  ProcessStartMode mode,
});

/// A request body larger than this is refused unread: a problem URL with
/// its JSON wrapper is well under 200 bytes.
const kMaxOpenBody = 4096;

/// Hands [url] to `xdg-open` as one argument (no shell), detached so the
/// browser outlives nothing of ours.
Future<void> xdgOpen(String url, {DetachedStarter start = Process.start}) =>
    start('xdg-open', [url], mode: ProcessStartMode.detached);

/// Answers one `/open` request; the caller closes the response.
///
/// Requires POST and `application/json`, so a page in some other browser
/// tab cannot trigger it with a plain form post (a cross-origin JSON POST
/// needs a CORS preflight this server never grants).
Future<void> handleOpen(HttpRequest request, UrlLauncher launch) async {
  final response = request.response;
  if (request.method != 'POST') {
    response.statusCode = HttpStatus.methodNotAllowed;
    return;
  }
  if (request.headers.contentType?.mimeType != 'application/json') {
    response.statusCode = HttpStatus.unsupportedMediaType;
    return;
  }
  final bytes = <int>[];
  await for (final chunk in request) {
    bytes.addAll(chunk);
    if (bytes.length > kMaxOpenBody) {
      response.statusCode = HttpStatus.requestEntityTooLarge;
      return;
    }
  }
  final url = _urlIn(bytes);
  if (url == null || !isProblemUrl(url)) {
    response.statusCode = HttpStatus.badRequest;
    return;
  }
  await launch(url);
  response.statusCode = HttpStatus.noContent;
}

/// The `url` string of a `{"url": ...}` body, or null for anything else.
String? _urlIn(List<int> bytes) {
  try {
    final body = jsonDecode(utf8.decode(bytes));
    return body is Map && body['url'] is String ? body['url'] as String : null;
  } on FormatException {
    return null;
  }
}

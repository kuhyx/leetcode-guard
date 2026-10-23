/// The desktop half of the app: serves the web build, the snapshot and the
/// one action the page needs a hand with.
///
/// `/snapshot.json` and `/heartbeat.json` come from a [SnapshotSource] that
/// reads a file on this machine (the exporter's copy, or a `--fixture`), so
/// the browser holds no credential and nothing here reads Firebase.
/// `POST /open` hands a problem page to the system browser (`open_route`).
/// Bound to loopback only.
library;

import 'dart:io';

import 'package:leetcode_guard/desktop/open_route.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/data/wrapper_snapshot_source.dart';
import 'package:leetcode_guard/src/data/wrapper_url_opener.dart';
import 'package:path/path.dart' as p;

/// Fixed on purpose: the origin keys the Chrome profile's localStorage (the
/// cached snapshot), so a different port is a fresh, empty app. Taken
/// nearby: 8771 (this repo's Python web server), 8773 (book-guard), 8774
/// (screen-locker workout-poke).
const kWrapperPort = 8776;

/// Serves [webRoot], [kSnapshotPath] and [kHeartbeatPath] from [source],
/// and [kOpenPath] through [open].
class WrapperServer {
  /// Creates a server; [open] defaults to [xdgOpen].
  new({required this.webRoot, required this.source, UrlLauncher? open})
    : open = open ?? xdgOpen;

  /// The Flutter web build.
  final String webRoot;

  /// Where the snapshot comes from (the local file, or a `--fixture`).
  final SnapshotSource source;

  /// Opens a vetted problem URL in the system browser.
  final UrlLauncher open;
  HttpServer? _server;

  /// Starts listening on loopback [port] (0 = any, for tests).
  Future<int> start({int port = kWrapperPort}) async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, port);
    _server = server;
    server.listen(_handle);
    return server.port;
  }

  /// Stops listening.
  Future<void> close() async => await _server?.close(force: true);

  Future<void> _handle(HttpRequest request) async {
    final response = request.response;
    try {
      final path = request.uri.path;
      if (path == kOpenPath) {
        await handleOpen(request, open);
      } else if (path == kSnapshotPath || path == kHeartbeatPath) {
        await _passThrough(
          response,
          path == kSnapshotPath ? source.fetch : source.heartbeat,
        );
      } else {
        await _static(response, request.uri.pathSegments);
      }
    } on SnapshotUnavailable catch (error) {
      response
        ..statusCode = HttpStatus.badGateway
        ..headers.contentType = ContentType.text
        ..write(error.message);
    } on Exception catch (error) {
      stderr.writeln('leetcode-guard app: ${request.uri.path}: $error');
      response.statusCode = HttpStatus.internalServerError;
    } finally {
      await response.close();
    }
  }

  Future<void> _passThrough(
    HttpResponse response,
    Future<String?> Function() read,
  ) async {
    // Never let the browser answer from its HTTP cache: a cached 200 would
    // hide an outage behind a fresh-looking fetch.
    response.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
    final body = await read();
    if (body == null) {
      response.statusCode = HttpStatus.notFound;
      return;
    }
    response
      ..headers.contentType = ContentType.json
      ..write(body);
  }

  Future<void> _static(HttpResponse response, List<String> segments) async {
    final relative = segments.isEmpty ? ['index.html'] : segments;
    final resolved = p.normalize(p.joinAll([webRoot, ...relative]));
    if (!p.isWithin(webRoot, resolved)) {
      response.statusCode = HttpStatus.forbidden;
      return;
    }
    final file = File(resolved);
    if (!file.existsSync()) {
      response.statusCode = HttpStatus.notFound;
      return;
    }
    response.headers.contentType = contentTypeFor(resolved);
    await response.addStream(file.openRead());
  }

  /// Content type for [filePath]. CanvasKit refuses a `.wasm` served as
  /// anything but `application/wasm`, and the app then renders nothing.
  static ContentType contentTypeFor(String filePath) =>
      switch (p.extension(filePath).toLowerCase()) {
        '.html' => ContentType.html,
        '.js' || '.mjs' => ContentType('text', 'javascript', charset: 'utf-8'),
        '.json' => ContentType.json,
        '.wasm' => ContentType('application', 'wasm'),
        '.css' => ContentType('text', 'css', charset: 'utf-8'),
        '.png' => ContentType('image', 'png'),
        '.svg' => ContentType('image', 'svg+xml'),
        '.ttf' => ContentType('font', 'ttf'),
        '.otf' => ContentType('font', 'otf'),
        '.woff2' => ContentType('font', 'woff2'),
        _ => ContentType.binary,
      };
}

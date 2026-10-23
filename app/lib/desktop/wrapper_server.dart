/// The desktop half of the app: serves the web build and the snapshot.
///
/// `/snapshot.json` is answered by a [SnapshotSource] running here, in the
/// wrapper, so the browser never holds the Firebase credential. Bound to
/// loopback only.
library;

import 'dart:io';

import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/data/wrapper_snapshot_source.dart';
import 'package:path/path.dart' as p;

/// Fixed on purpose: the origin keys the Chrome profile's localStorage (the
/// cached snapshot), so a different port is a fresh, empty app. Taken
/// nearby: 8771 (this repo's Python web server), 8773 (book-guard), 8774
/// (screen-locker workout-poke).
const kWrapperPort = 8776;

/// Serves [webRoot], [kSnapshotPath] and [kHeartbeatPath] from [source].
class WrapperServer {
  /// Creates a server.
  new({required this.webRoot, required this.source});

  /// The Flutter web build.
  final String webRoot;

  /// Where the snapshot comes from (Firebase, or a `--fixture` file).
  final SnapshotSource source;
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
      if (path == kSnapshotPath || path == kHeartbeatPath) {
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

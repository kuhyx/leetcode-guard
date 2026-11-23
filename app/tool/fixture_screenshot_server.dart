/// Dev only: the real wrapper over a fixture snapshot, for screenshots.
///
/// Serves `build/web` and the fixture on a free loopback port (never 8776,
/// which kuhy's live app may hold), with `generated_at` restamped to now on
/// every read so the shot shows no stale banner. No relay: the Coach tab's
/// session is not part of these shots (`coach_screenshot_server.dart` is).
///
/// Usage: `dart run tool/fixture_screenshot_server.dart PORT_FILE FIXTURE`
/// (writes the wrapper port to PORT_FILE; serves until killed).
library;

import 'dart:convert';
import 'dart:io';

import 'package:leetcode_guard/desktop/sources.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';

/// The fixture with a fresh `generated_at`.
class _FreshFixture extends FileSnapshotSource {
  new(super.file);

  @override
  Future<String?> fetch() async {
    final json = jsonDecode((await super.fetch())!) as Map<String, Object?>;
    json['generated_at'] = DateTime.now().toUtc().toIso8601String();
    return jsonEncode(json);
  }
}

Future<void> main(List<String> args) async {
  final wrapper = WrapperServer(
    webRoot: '${Directory.current.path}/build/web',
    source: _FreshFixture(File(args[1])),
  );
  final port = await wrapper.start(port: 0);
  File(args.first).writeAsStringSync('$port');
  stdout.writeln('wrapper on http://localhost:$port');
}

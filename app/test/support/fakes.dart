import 'package:leetcode_guard/src/data/snapshot_cache.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';

/// A source answering from queues: each entry is a body, null (nothing
/// published) or an [Exception] to throw. The last entry repeats.
class FakeSource implements SnapshotSource {
  new(this.answers, {this.heartbeats = const [null]});

  final List<Object?> answers;
  final List<Object?> heartbeats;
  int calls = 0;
  int beats = 0;

  static String? _next(List<Object?> queue, int index) {
    final answer = queue[index < queue.length ? index : queue.length - 1];
    if (answer is Exception) throw answer;
    return answer as String?;
  }

  @override
  Future<String?> fetch() async => _next(answers, calls++);

  @override
  Future<String?> heartbeat() async => _next(heartbeats, beats++);
}

/// An in-memory [SnapshotCache].
class MemoryCache implements SnapshotCache {
  new([this.value]);

  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String raw) async => value = raw;
}

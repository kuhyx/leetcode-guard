/// The fake relay *client*: a [CoachTransport] over [FakeRelay], with the
/// failure switches the tests need (relay down, network, slow answers).
library;

import 'dart:convert';

import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';

import 'fake_relay.dart';

/// A mutable clock both the controller and the relay read.
class TestClock {
  new([DateTime? start]) : now = start ?? DateTime.utc(2026, 10, 23, 15, 4, 48);

  DateTime now;

  DateTime call() => now;

  int get ms => now.millisecondsSinceEpoch;

  void advance(Duration d) => now = now.add(d);
}

/// A fixed device id.
class FixedDeviceId implements DeviceIdStore {
  @override
  Future<String> deviceId() async => '0b8f3c2e-5d1a-4f6b-9c7d-2e4a6b8c0d1e';
}

class FakeCoachTransport implements CoachTransport {
  new(this.clock, {this.phone = false})
    : relay = FakeRelay(now: () => clock.ms);

  final TestClock clock;
  final FakeRelay relay;

  @override
  final bool phone;

  /// Thrown by every call while set.
  CoachUnavailable? outage;

  /// Polls a request waits (queued, then working) before it runs.
  int pollsBeforeAnswer = 1;

  /// Never answer: the 300 s "no reply" path.
  bool silent = false;

  /// The relay forgets results (a restart) on the next poll.
  bool forgetOnce = false;

  /// Heartbeat reads so far.
  int heartbeats = 0;

  /// Every `req` sent, in order, with its rid.
  final List<(String, Map<String, Object?>)> sent = [];
  final Map<String, Map<String, Object?>> _queued = {};
  final Map<String, int> _polls = {};

  @override
  Duration get resultPollEvery =>
      phone ? const Duration(seconds: 2) : const Duration(seconds: 1);

  void _check() {
    if (outage case final CoachUnavailable e) throw e;
  }

  // Round-trips through JSON, as the wire would.
  static Object? _wire(Object? value) => jsonDecode(jsonEncode(value));

  @override
  Future<RelayResult?> submit(String rid, Map<String, Object?> req) async {
    _check();
    sent.add((rid, req));
    final done = relay.done[rid];
    if (done != null) return RelayResult.tryParse(_wire(done));
    _queued[rid] = req;
    return null;
  }

  @override
  Future<RelayResult?> result(String rid) async {
    _check();
    if (forgetOnce) {
      forgetOnce = false;
      _queued.remove(rid);
      throw const CoachUnavailable(CoachOutage.forgotten, 'unknown rid');
    }
    final done = relay.done[rid];
    if (done != null) return RelayResult.tryParse(_wire(done));
    final req = _queued[rid];
    if (req == null || silent) return null;
    final polls = _polls[rid] = (_polls[rid] ?? 0) + 1;
    if (polls <= pollsBeforeAnswer) {
      relay.busy = rid;
      return null;
    }
    relay.busy = null;
    _queued.remove(rid);
    final result = relay.handle(
      rid,
      req['kind']! as String,
      (req['body']! as Map).cast<String, Object?>(),
    );
    return RelayResult.tryParse(_wire(result));
  }

  @override
  Future<Heartbeat?> heartbeat() async {
    heartbeats++;
    _check();
    return Heartbeat.tryParse(_wire(relay.heartbeat));
  }

  @override
  Future<CoachState?> state() async {
    _check();
    return CoachState.tryParse(_wire(relay.state));
  }

  @override
  Future<List<ChatMessage>> chat({String? after}) async {
    _check();
    return chatFrom(_wire(relay.chat), after: after);
  }
}

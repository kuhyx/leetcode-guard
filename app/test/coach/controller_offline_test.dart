// Offline-first (kuhy, 2026-11-27): a request lands in the local outbox
// before the network, is sent again by itself once the relay is reachable,
// survives a restart, and the pulled thread shows on a cold start offline.
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/local_store.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_coach_transport.dart';

const _net = CoachUnavailable(CoachOutage.network, 'offline');

/// A transport whose submit can fail on its own (the relay still beats).
class _Flaky extends FakeCoachTransport {
  new(super.clock);

  CoachUnavailable? submitError;

  @override
  Future<RelayResult?> submit(String rid, Map<String, Object?> req) async {
    if (submitError case final CoachUnavailable e) throw e;
    return await super.submit(rid, req);
  }
}

void main() {
  late TestClock clock;
  late _Flaky transport;
  late MemoryCoachStore disk;
  late CoachController c;

  CoachController make() => CoachController(
    transport: transport,
    devices: FixedDeviceId(),
    store: disk,
    ulid: UlidGenerator(now: () => clock.ms),
    clock: clock.call,
  );

  Future<void> run(int seconds) async {
    for (var i = 0; i < seconds; i++) {
      clock.advance(const Duration(seconds: 1));
      await c.tick();
    }
  }

  Future<void> settle() async {
    for (var i = 0; i < 40 && c.busy; i++) {
      await run(1);
    }
  }

  Future<void> start() async {
    await c.refresh();
    expect(c.startSession('missing-number'), isTrue);
    await settle();
  }

  /// The app was killed: a new controller over the same device storage.
  Future<void> restart() async {
    c.dispose();
    c = make();
    await c.restore();
  }

  setUp(() {
    clock = TestClock();
    transport = _Flaky(clock);
    disk = MemoryCoachStore();
    c = make();
  });

  tearDown(() => c.dispose());

  test('a failed send is sent again by itself once the relay answers, '
      'under the same rid, with no tap', () async {
    await start();
    transport.submitError = _net;
    expect(c.gradeText(1, 'O(1) extra space'), isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(c.pending!.phase, RequestPhase.notSent);
    final rid = c.pending!.rid;
    transport.submitError = null;
    await settle();
    expect(c.pending, isNull);
    expect(transport.sent.last.$1, rid);
    expect(c.gradeData(1)!['grade'], isNotNull);
  });

  test('a request typed while the relay is unreachable is kept, shown as '
      'pending, and delivered when it is back', () async {
    await start();
    transport.outage = _net;
    await c.refresh();
    expect(c.presence, CoachPresence.unreachable);
    expect(c.sendChat('why does xor cancel?'), isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(c.pending!.body['text'], 'why does xor cancel?');
    expect(disk.values[kOutboxKey], contains('why does xor cancel?'));
    transport.outage = null;
    await settle();
    expect(c.pending, isNull);
    expect(disk.values[kOutboxKey], isNull);
    expect(c.messages.map((m) => m.text), contains('why does xor cancel?'));
  });

  test('an unsent answer survives a restart and is sent by itself', () async {
    await start();
    transport.submitError = _net;
    expect(c.gradeText(1, 'O(1) extra space'), isTrue);
    await Future<void>.delayed(Duration.zero);
    final rid = c.pending!.rid;
    transport.submitError = null;
    await restart();
    expect(c.pending!.rid, rid);
    expect(c.pending!.body['answer'], 'O(1) extra space');
    await c.refresh();
    await settle();
    expect(c.pending, isNull);
    expect(transport.sent.last.$1, rid);
  });

  test('a request the relay already took is only polled after a restart, '
      'never sent twice', () async {
    await start();
    transport.silent = true;
    expect(c.hint(), isTrue);
    await Future<void>.delayed(Duration.zero);
    final sends = transport.sent.length;
    await restart();
    expect(c.pending!.phase, RequestPhase.queued);
    transport.silent = false;
    await c.refresh();
    await settle();
    expect(c.pending, isNull);
    expect(transport.sent, hasLength(sends));
    expect(c.state!.rung, 'H0');
  });

  test(
    'a cold start with the relay unreachable shows the last thread',
    () async {
      await start();
      expect(c.gradeText(1, 'O(1) extra space'), isTrue);
      await settle();
      final keys = c.messages.map((m) => m.key).toList();
      final sid = c.sid;
      expect(keys, isNotEmpty);
      transport.outage = _net;
      await restart();
      expect(c.messages.map((m) => m.key), keys);
      expect(c.sid, sid);
      expect(c.gradeData(1), isNotNull);
      await c.refresh();
      expect(c.presence, CoachPresence.unreachable);
      expect(c.messages.map((m) => m.key), keys, reason: 'kept, not cleared');
    },
  );

  test('nothing can be sent before the local copy is read', () {
    expect(c.canAct, isFalse);
  });

  test('an unreadable local copy is ignored', () async {
    disk.values[kOutboxKey] = '{not json';
    disk.values[kThreadKey] = '[1]';
    await c.restore();
    expect(c.pending, isNull);
    expect(c.state, isNull);
    expect(decodeOutbox('{"rid":"x","kind":"hint","body":{}}'), isNull);
    final t = decodeThread(
      '{"messages":[{"key":"bad"},{"key":"m0001","text":"hi"},3],'
      '"grades":{"x":{},"2":{"grade":"pass"},"3":1}}',
    )!;
    expect(t.messages.single.text, 'hi');
    expect(t.grades.keys, [2]);
    expect(t.state, isNull);
  });

  test('PrefsCoachStore round-trips and clears', () async {
    SharedPreferences.setMockInitialValues({});
    final store = PrefsCoachStore();
    expect(await store.read(kOutboxKey), isNull);
    await store.write(kOutboxKey, 'x');
    expect(await store.read(kOutboxKey), 'x');
    await store.write(kOutboxKey, null);
    expect(await store.read(kOutboxKey), isNull);
  });
}

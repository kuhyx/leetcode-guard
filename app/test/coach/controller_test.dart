import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';

import '../support/fake_coach_transport.dart';

const _net = CoachUnavailable(CoachOutage.network, 'offline');

/// A transport whose submit refuses or answers as the test says.
class _Scripted extends FakeCoachTransport {
  new(super.clock);

  CoachUnavailable? submitError;
  RelayResult? answer;

  @override
  Future<RelayResult?> submit(String rid, Map<String, Object?> req) async {
    if (submitError case final CoachUnavailable e) throw e;
    if (answer case final RelayResult r) {
      sent.add((rid, req));
      return r;
    }
    return await super.submit(rid, req);
  }
}

void main() {
  late TestClock clock;
  late _Scripted transport;
  late CoachController c;

  Future<void> run(int seconds) async {
    for (var i = 0; i < seconds; i++) {
      clock.advance(const Duration(seconds: 1));
      await c.tick();
    }
  }

  /// Runs the poll loop until nothing is in flight or pausing.
  Future<void> settle() async {
    for (var i = 0; i < 12 && c.busy; i++) {
      await run(1);
    }
  }

  Future<void> start() async {
    await c.refresh();
    expect(c.startSession('missing-number'), isTrue);
    await settle();
  }

  setUp(() {
    clock = TestClock();
    transport = _Scripted(clock);
    c = CoachController(
      transport: transport,
      devices: FixedDeviceId(),
      ulid: UlidGenerator(now: () => clock.ms),
      clock: clock.call,
    );
  });

  tearDown(() => c.dispose());

  test('checking until the first heartbeat, then online', () async {
    expect(c.presence, CoachPresence.checking);
    expect(c.canAct, isFalse);
    expect(c.startSession('missing-number'), isFalse);
    await c.refresh();
    expect(c.presence, CoachPresence.online);
    expect(c.sid, isNull);
  });

  test('a phone with no heartbeat at all is PC offline', () async {
    final phone = _NoBeat(clock);
    final p = CoachController(transport: phone, devices: FixedDeviceId());
    await p.refresh();
    expect(p.presence, CoachPresence.pcOffline);
    p.dispose();
  });

  test('the network down is "unreachable", and clears', () async {
    transport.outage = _net;
    await c.refresh();
    expect(c.presence, CoachPresence.unreachable);
    transport.outage = null;
    await c.refresh();
    expect(c.presence, CoachPresence.online);
  });

  test('a failed send keeps its rid; "retry" re-sends the same one', () async {
    await start();
    transport.submitError = _net;
    expect(c.hint(), isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(c.pending!.phase, RequestPhase.notSent);
    final rid = c.pending!.rid;
    transport.submitError = null;
    await c.resend();
    await settle();
    expect(transport.sent.last.$1, rid);
    expect(c.pending, isNull);
    expect(c.state!.rung, 'H0');
  });

  test('resend does nothing for a request that is still running', () async {
    await start();
    c.hint();
    await Future<void>.delayed(Duration.zero);
    final count = transport.sent.length;
    await c.resend();
    expect(transport.sent, hasLength(count));
  });

  test('a refused send (HTTP 400) becomes a failure, not a hang', () async {
    await start();
    transport.submitError = const CoachUnavailable(
      CoachOutage.rejected,
      'The relay refused the request (HTTP 413)',
    );
    c.hint();
    await Future<void>.delayed(Duration.zero);
    expect(c.pending, isNull);
    expect(c.failure!.text, contains('413'));
    expect(c.failure!.retry, isFalse);
    expect(c.retryFailure(), isFalse);
  });

  test('retry:true is sent again under a NEW rid', () async {
    await start();
    transport.answer = RelayResult.fromJson({
      'ok': false,
      'code': 'rate_limited',
      'error': 'slow down',
      'retry': true,
      'retry_after_ms': 3000,
    });
    c.hint();
    await Future<void>.delayed(Duration.zero);
    expect(c.failure!.code, 'rate_limited');
    final first = transport.sent.last.$1;
    expect(c.retryFailure(), isFalse, reason: 'still in the 3 s pause');
    await settle();
    transport.answer = null;
    expect(c.retryFailure(), isTrue);
    await settle();
    expect(transport.sent.last.$1, isNot(first));
    expect(c.failure, isNull);
  });

  test('a relay that forgot the rid gets the same request again', () async {
    await start();
    c.hint();
    await Future<void>.delayed(Duration.zero);
    final rid = c.pending!.rid;
    transport.forgetOnce = true;
    await run(1);
    expect(transport.sent.last.$1, rid);
    await settle();
    expect(c.pending, isNull);
  });

  test('a network blip while polling keeps the request', () async {
    await start();
    c.hint();
    await Future<void>.delayed(Duration.zero);
    transport.outage = _net;
    await run(1);
    expect(c.pending, isNotNull);
    expect(c.presence, CoachPresence.unreachable);
    transport.outage = null;
    await settle();
    expect(c.pending, isNull);
  });

  test('attach polls while any screen is up; detach is counted', () async {
    c
      ..attach()
      ..attach()
      ..detach()
      ..detach()
      ..detach();
    await Future<void>.delayed(Duration.zero);
    expect(c.presence, CoachPresence.online);
  });

  test('requests outside their bounds are never sent', () async {
    await c.refresh();
    expect(c.startSession('Not A Slug'), isFalse);
    expect(c.sendChat('hi'), isFalse, reason: 'no session');
    await start();
    expect(c.sendChat('   '), isFalse);
    expect(c.sendChat('x' * (kMaxTextBytes + 1)), isFalse);
    expect(c.gradeText(1, ''), isFalse);
    expect(c.gradePicks(const []), isFalse);
    expect(c.gradePicks(List.filled(kMaxPicks + 1, 'a')), isFalse);
    expect(c.runCode('   '), isFalse);
    expect(c.endSession(), isTrue);
    await settle();
    expect(c.state!.session!.endReason, 'ended');
    expect(c.sid, isNull);
  });

  test('step 3 sends only names the toolbox offers: a stale pick has no '
      'checkbox to clear, so it would be refused forever', () async {
    await start();
    expect(c.gradeText(1, 'O(1) extra space'), isTrue);
    await settle();
    expect(c.gradeText(2, 'pairs cancel\nindices 0..n'), isTrue);
    await settle();
    expect(c.state!.step, 3);
    expect(c.gradePicks(const ['renamed tool']), isFalse);
    expect(c.gradePicks(const ['renamed tool', 'XOR']), isTrue);
    await settle();
    expect(transport.relay.ran.last.$2['picks'], ['XOR']);
    expect(c.failure, isNull);
  });

  test('code helpers', () {
    expect(codeOf('look:\n```js\nreturn 1;\n```\nok?'), 'return 1;');
    expect(codeOf(' x = 1; '), 'x = 1;');
    expect(looksLikeCode('```\nfoo\n```'), isTrue);
    expect(looksLikeCode('const a = 1'), isTrue);
    expect(looksLikeCode('why does xor work?'), isFalse);
  });

  test('refused() stands in for a request refused at the door', () {
    final r = CoachController.refused('too big');
    expect(r.ok, isFalse);
    expect(r.error, 'too big');
  });
}

class _NoBeat extends FakeCoachTransport {
  new(super.clock) : super(phone: true);

  @override
  Future<Heartbeat?> heartbeat() async => null;
}

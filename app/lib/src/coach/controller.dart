/// The coach session as the app sees it: the relay's state and chat, the
/// one request in flight, and whether the PC is there at all.
///
/// Every timing is `DOCS-coach-relay.md` §1's: a result is polled every 1 s
/// (desktop) or 2 s (phone); the heartbeat every 5 s with a live session or
/// a request out, every 30 s otherwise, and only while a coach screen is
/// visible (`attach`); 300 s without a result offers "send again" with the
/// same rid; actions pause 3 s after each result; on the phone a beat older
/// than 2 min is "PC offline". Time comes from an injected clock, so tests
/// drive all of it without real waiting.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';

part 'controller_send.dart';

/// Whether the PC's relay can take a request.
enum CoachPresence {
  /// Not heard from yet.
  checking,

  /// Beating.
  online,

  /// Phone: no heartbeat in 2 min (or none ever written).
  pcOffline,

  /// Desktop: the wrapper says the relay service is not running.
  relayDown,

  /// The network, Firebase or the Sync account is the problem.
  unreachable,
}

/// Holds the session and talks to the relay over [transport].
class CoachController extends ChangeNotifier {
  /// Creates the controller; [ulid] and [clock] are injected for tests.
  new({
    required this.transport,
    required this.devices,
    this.reporter,
    UlidGenerator? ulid,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now,
       _ulid = ulid ?? UlidGenerator();

  /// The path to the relay.
  final CoachTransport transport;

  /// This install's `dev`.
  final DeviceIdStore devices;

  /// Keeps outages for the desktop and sends them once a beat lands.
  final ErrorReporter? reporter;
  final UlidGenerator _ulid;
  final DateTime Function() _clock;

  /// The relay's state, kept (greyed) while the PC is away.
  CoachState? state;

  /// The chat, in key order.
  final List<ChatMessage> messages = [];

  /// The last heartbeat read.
  Heartbeat? heartbeat;

  /// Why the relay cannot be reached, or null.
  CoachUnavailable? outage;

  /// The request in flight, or null.
  PendingRequest? pending;

  /// The last request the relay refused, until the next one is sent.
  RelayFailure? failure;

  final Map<int, Json> _grades = {};
  String? _dev;
  bool _beatRead = false;
  DateTime? _cooldownUntil;
  DateTime? _lastBeat;
  DateTime? _lastResult;
  Timer? _timer;
  int _attached = 0;
  bool _ticking = false;

  /// The injected clock's now.
  DateTime now() => _clock();

  /// Whether the PC can take a request right now.
  CoachPresence get presence {
    final o = outage?.outage;
    if (o == CoachOutage.relayDown) return CoachPresence.relayDown;
    if (o != null) return CoachPresence.unreachable;
    if (!_beatRead) return CoachPresence.checking;
    final beat = heartbeat?.beat;
    if (beat == null) return CoachPresence.pcOffline;
    final age = now().millisecondsSinceEpoch - beat;
    return transport.phone && age > kOfflineAfter.inMilliseconds
        ? CoachPresence.pcOffline
        : CoachPresence.online;
  }

  /// A request is out or the 3 s pause after one is running.
  bool get busy {
    final until = _cooldownUntil;
    return pending != null || (until != null && now().isBefore(until));
  }

  /// Whether Send / Grade / Hint / Reveal / Run may be pressed.
  bool get canAct => presence == CoachPresence.online && !busy;

  /// The live sid, or null.
  String? get sid => (state?.live ?? false) ? state?.session?.id : null;

  /// The data of step [n]'s last grade this session (cards for step 5).
  Json? gradeData(int n) => _grades[n];

  /// A coach screen became visible: poll while at least one is.
  void attach() {
    if (_attached++ > 0) return;
    unawaited(refresh());
    _timer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => unawaited(tick()),
    );
  }

  /// A coach screen went away (or the app went to the background).
  void detach() {
    if (_attached == 0 || --_attached > 0) return;
    _timer?.cancel();
    _timer = null;
  }

  /// Reads the heartbeat, then state and chat.
  Future<void> refresh() async {
    await _beat();
    await _sync();
    notifyListeners();
  }

  bool _due(DateTime? last, Duration every) =>
      last == null || !now().isBefore(last.add(every));

  /// One second of the poll loop.
  Future<void> tick() async {
    if (_ticking) return;
    _ticking = true;
    try {
      final p = pending;
      if (p != null &&
          p.phase != RequestPhase.notSent &&
          _due(_lastResult, transport.resultPollEvery)) {
        await _poll(p);
      }
      final live = (state?.live ?? false) || pending != null;
      if (_due(_lastBeat, live ? kBeatLive : kBeatIdle)) await _beat();
      final still = pending;
      if (still != null &&
          (still.phase == RequestPhase.queued ||
              still.phase == RequestPhase.working) &&
          !now().isBefore(still.sentAt.add(kStallAfter))) {
        still.phase = RequestPhase.stalled;
      }
    } finally {
      _ticking = false;
    }
    notifyListeners();
  }

  // Only these say the relay is unreachable; rejected / forgotten are
  // about one request and are handled where it is.
  static const Set<CoachOutage> _unreachable = {
    CoachOutage.relayDown,
    CoachOutage.network,
    CoachOutage.signedOut,
  };

  void _setOutage(CoachUnavailable e) {
    if (!_unreachable.contains(e.outage)) return;
    outage = e;
    unawaited(reporter?.failed(e.message));
  }

  Future<void> _beat() async {
    _lastBeat = now();
    try {
      final hb = await transport.heartbeat();
      heartbeat = hb;
      outage = null;
      unawaited(reporter?.reached());
      _beatRead = true;
      final p = pending;
      if (p != null && p.phase == RequestPhase.queued && hb?.busy == p.rid) {
        p.phase = RequestPhase.working;
      }
      final rev = hb?.stateRev;
      if (rev != null && rev != state?.rev) await _sync();
    } on CoachUnavailable catch (e) {
      _setOutage(e);
    }
  }

  Future<void> _sync() async {
    try {
      final next = await transport.state();
      if (next?.session?.id != state?.session?.id) {
        messages.clear();
        _grades.removeWhere((_, data) => data['session'] != next?.session?.id);
      }
      state = next;
      final after = messages.isEmpty ? null : messages.last.key;
      messages.addAll(await transport.chat(after: after));
    } on CoachUnavailable catch (e) {
      _setOutage(e);
    }
  }

  /// A result standing for a request the relay refused at the door.
  static RelayResult refused(String message) => RelayResult.fromJson({
    'ok': false,
    'code': 'bad_request',
    'error': message,
    'retry': false,
  });

  /// [notifyListeners] for the request half (`controller_send.dart`),
  /// which, as an extension, may not call the protected member itself.
  void _changed() => notifyListeners();

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

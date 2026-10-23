part of 'controller.dart';

/// No result for this long: "No reply from PC, send again".
const kStallAfter = Duration(seconds: 300);

/// Actions stay disabled this long after a result (the relay's pace).
const kCooldown = Duration(seconds: 3);

/// Phone: a heartbeat older than this is "PC offline".
const kOfflineAfter = Duration(minutes: 2);

/// Heartbeat cadence with a live session (or a request out) / otherwise.
const kBeatLive = Duration(seconds: 5);

/// See [kBeatLive].
const kBeatIdle = Duration(seconds: 30);

/// The request half of [CoachController]: sending, re-sending, polling
/// for the result and taking it in.
extension CoachSending on CoachController {
  /// Sends request [kind] with [body] under a fresh rid; false when an
  /// action is not allowed right now.
  bool send(String kind, Json body) {
    if (!canAct) return false;
    final p = PendingRequest(_ulid.next(), kind, body, sentAt: now());
    pending = p;
    failure = null;
    _changed();
    unawaited(_submit(p));
    return true;
  }

  /// Sends the stalled or unsent request again, under the SAME rid.
  Future<void> resend() async {
    final p = pending;
    if (p == null || !p.resendable) return;
    await _submit(p);
  }

  /// Sends a `retry:true` failure again as a NEW rid.
  bool retryFailure() {
    final f = failure;
    if (f == null || !f.retry) return false;
    return send(f.kind, f.body);
  }

  Future<void> _submit(PendingRequest p) async {
    p
      ..phase = RequestPhase.queued
      ..sentAt = now();
    _lastResult = now();
    _changed();
    try {
      final dev = _dev ??= await devices.deviceId();
      final r = await transport.submit(p.rid, {
        'kind': p.kind,
        'dev': dev,
        'body': p.body,
      });
      if (r != null) await _finish(p, r);
    } on CoachUnavailable catch (e) {
      if (e.outage == CoachOutage.rejected) {
        await _finish(p, CoachController.refused(e.message));
      } else {
        p
          ..phase = RequestPhase.notSent
          ..error = e.message;
        _setOutage(e);
      }
    }
    _changed();
  }

  Future<void> _poll(PendingRequest p) async {
    _lastResult = now();
    try {
      final r = await transport.result(p.rid);
      if (r != null) await _finish(p, r);
    } on CoachUnavailable catch (e) {
      // A restarted relay forgot the rid: the same request, the same rid.
      if (e.outage == CoachOutage.forgotten) {
        await _submit(p);
        return;
      }
      _setOutage(e);
    }
  }

  Future<void> _finish(PendingRequest p, RelayResult r) async {
    if (!identical(pending, p)) return;
    pending = null;
    _cooldownUntil = now().add(kCooldown);
    if (!r.ok) {
      failure = RelayFailure(p.kind, p.body, r);
    } else if (p.kind == 'grade_step') {
      final n = readInt(r.data['step']) ?? readInt(p.body['step']) ?? 0;
      _grades[n] = {...r.data, 'session': p.body['session']};
    }
    await _sync();
    _changed();
  }
}

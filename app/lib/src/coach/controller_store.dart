part of 'controller.dart';

/// The local half of [CoachController]: the outbox and the thread on the
/// device (`local_store.dart`), so a request is saved before the network
/// sees it and a cold start offline still shows the session.
extension CoachLocalCopy on CoachController {
  /// Reads the outbox and the thread back, once; actions wait for it, so a
  /// new request can never overwrite one a previous run left unsent.
  Future<void> restore() => _restoring ??= _readLocal();

  Future<void> _readLocal() async {
    final thread = decodeThread(await store.read(kThreadKey));
    if (thread != null && state == null && messages.isEmpty) {
      state = thread.state;
      messages.addAll(thread.messages);
      _grades.addAll(thread.grades);
    }
    final kept = decodeOutbox(await store.read(kOutboxKey));
    if (kept != null && pending == null) pending = kept;
    _restored = true;
    _changed();
  }

  /// Saves [p] as the outbox while it is still the request in flight;
  /// null empties it (answered).
  Future<void> _saveOutbox(PendingRequest? p, {bool sent = false}) async {
    if (p == null) {
      await store.write(kOutboxKey, null);
    } else if (identical(pending, p)) {
      await store.write(kOutboxKey, encodeOutbox(p, sent: sent));
    }
  }

  Future<void> _saveThread() async =>
      await store.write(kThreadKey, encodeThread(state, messages, _grades));
}

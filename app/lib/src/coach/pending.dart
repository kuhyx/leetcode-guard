/// A request in flight, and a request the relay answered with an error.
library;

import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/json_read.dart';

/// Where an in-flight request stands.
enum RequestPhase {
  /// Sent; the relay has not started it.
  queued,

  /// `heartbeat.busy` names it: the coach is on it.
  working,

  /// No result after 300 s: offer "send again" (the same rid).
  stalled,

  /// The send itself failed: offer "retry" (the same rid).
  notSent,
}

/// One request with its identity fixed: every resend reuses [rid], so the
/// relay's done-map re-answers a finished one instead of running it twice.
class PendingRequest {
  /// Creates the request, first sent at [sentAt].
  new(this.rid, this.kind, this.body, {required this.sentAt, this.runKey});

  /// The ULID.
  final String rid;

  /// One of the seven kinds.
  final String kind;

  /// The kind's body.
  final Json body;

  /// For `run_code`: the chat message whose code runs.
  final String? runKey;

  /// When it was last (re)sent; the 300 s stall counts from here.
  DateTime sentAt;

  /// Where it stands.
  RequestPhase phase = RequestPhase.queued;

  /// Why the last send failed ([RequestPhase.notSent]).
  String? error;

  /// The banner's words.
  String get text => switch (phase) {
    RequestPhase.queued => 'Queued on the PC...',
    RequestPhase.working => 'The coach is working...',
    RequestPhase.stalled => 'No reply from PC, send again',
    RequestPhase.notSent => 'Not sent: ${error ?? 'network error'}',
  };

  /// Whether the user may resend it (same rid).
  bool get resendable =>
      phase == RequestPhase.stalled || phase == RequestPhase.notSent;
}

/// A request the relay answered `ok:false`.
class RelayFailure {
  /// Wraps [result] for the request [kind] with [body].
  new(this.kind, this.body, this.result);

  /// The request kind.
  final String kind;

  /// Its body, kept so a `retry:true` error can be sent again (new rid).
  final Json body;

  /// The result.
  final RelayResult result;

  /// The error code.
  String? get code => result.code;

  /// Whether sending again may work.
  bool get retry => result.retry;

  /// The words to show: the relay's own, plus any extra it gave.
  String get text {
    final base = result.error ?? 'The relay refused it (${code ?? 'error'})';
    final note = readString(result.raw['note']);
    final resets = _resetsAt(result.raw['resets_at']);
    return [
      base,
      if (note != null && note != base) note,
      if (resets != null) 'Claude is back $resets',
    ].join('\n');
  }

  // The contract does not type `resets_at`: unix ms (as every other time)
  // or a preformatted string are both shown.
  static String? _resetsAt(Object? value) {
    final ms = readInt(value);
    if (ms != null) {
      final t = DateTime.fromMillisecondsSinceEpoch(ms);
      return 'at ${asOf(t).substring('as of '.length)}';
    }
    return switch (readString(value)) {
      final String s => 'at $s',
      null => null,
    };
  }
}

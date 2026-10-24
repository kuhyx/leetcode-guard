/// The last few errors the phone showed, kept until the desktop has them.
///
/// The phone cannot report while offline, which is exactly when most of its
/// errors happen, so each one is kept here (message, first-seen, last-seen,
/// count) and sent on the next successful Firebase contact
/// (`app_error_report.dart`). Messages are already sanitised at the source
/// (`failure_text.dart`); they are scrubbed once more before being kept,
/// because this is persisted and then published.
library;

import 'dart:convert';

import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// How many distinct errors are kept.
const kKeepErrors = 5;

/// One distinct error message and when it was seen.
class AppError {
  /// Creates an entry.
  new(this.message, this.firstSeen, this.lastSeen, this.count);

  /// The sanitised text the app showed.
  final String message;

  /// When it was first seen (UTC); the desktop dedupes on this.
  final DateTime firstSeen;

  /// When it was last seen (UTC).
  DateTime lastSeen;

  /// How many times it was seen.
  int count;

  /// The wire and storage form.
  Json toJson() => {
    'message': message,
    'first_seen': firstSeen.toUtc().toIso8601String(),
    'last_seen': lastSeen.toUtc().toIso8601String(),
    'count': count,
  };

  /// Parses [toJson]'s form; null for anything else.
  static AppError? tryParse(Object? raw) {
    if (raw is! Json) return null;
    final message = raw['message'];
    final first = DateTime.tryParse('${raw['first_seen']}');
    final last = DateTime.tryParse('${raw['last_seen']}');
    final count = readInt(raw['count']);
    if (message is! String || first == null || last == null || count == null) {
      return null;
    }
    return AppError(message, first, last, count);
  }
}

/// A single persisted string.
abstract interface class TextSlot {
  /// The stored text, or null.
  Future<String?> read();

  /// Replaces the stored text.
  Future<void> write(String text);
}

/// [TextSlot] in `shared_preferences`.
class PrefsTextSlot implements TextSlot {
  /// Creates the slot under [key].
  const new(this.key);

  /// The preferences key.
  final String key;

  @override
  Future<String?> read() async =>
      (await SharedPreferences.getInstance()).getString(key);

  @override
  Future<void> write(String text) async =>
      await (await SharedPreferences.getInstance()).setString(key, text);
}

/// What one upload carries; [AppErrorLog.markSent] with it once it landed.
class ErrorBatch {
  /// Creates a batch.
  const new(this.body, this.rev);

  /// The JSON document to publish.
  final String body;

  /// The log revision it was taken at.
  final int rev;
}

/// The kept errors plus which revision of them the desktop already has.
class AppErrorLog {
  /// Creates the log; [slot] and [clock] are injected for tests.
  new({TextSlot? slot, DateTime Function()? clock, this.keep = kKeepErrors})
    : _slot = slot ?? const PrefsTextSlot('app_errors.log'),
      _clock = clock ?? DateTime.now;

  /// How many distinct errors are kept.
  final int keep;
  final TextSlot _slot;
  final DateTime Function() _clock;
  List<AppError>? _errors;
  int _rev = 0;
  int _sent = 0;

  Future<List<AppError>> _load() async {
    final loaded = _errors;
    if (loaded != null) return loaded;
    Object? raw;
    try {
      raw = jsonDecode(await _slot.read() ?? '{}');
    } on FormatException {
      raw = null;
    }
    final json = raw is Json ? raw : const <String, Object?>{};
    final list = json['errors'];
    _rev = readInt(json['rev']) ?? 0;
    _sent = readInt(json['sent']) ?? 0;
    return _errors = [
      if (list is List) ...list.map(AppError.tryParse).nonNulls,
    ];
  }

  Future<void> _save() => _slot.write(
    jsonEncode({
      'rev': _rev,
      'sent': _sent,
      'errors': [for (final e in _errors!) e.toJson()],
    }),
  );

  /// The kept errors, most recently seen first.
  Future<List<AppError>> entries() async => List.of(await _load());

  /// Notes one occurrence of [message].
  Future<void> record(String message) async {
    final errors = await _load();
    final text = scrubSecrets(message);
    final now = _clock().toUtc();
    final index = errors.indexWhere((e) => e.message == text);
    final entry = index < 0 ? AppError(text, now, now, 0) : errors[index];
    if (index >= 0) errors.removeAt(index);
    errors.insert(
      0,
      entry
        ..lastSeen = now
        ..count += 1,
    );
    if (errors.length > keep) errors.removeRange(keep, errors.length);
    _rev += 1;
    await _save();
  }

  /// What to publish for [device], or null when the desktop is up to date.
  Future<ErrorBatch?> pending(String device) async {
    final errors = await _load();
    if (_rev == _sent || errors.isEmpty) return null;
    final body = jsonEncode({
      'device': device,
      'sent_at': _clock().toUtc().toIso8601String(),
      'errors': [for (final e in errors) e.toJson()],
    });
    return ErrorBatch(body, _rev);
  }

  /// [batch] landed; anything recorded since stays pending.
  Future<void> markSent(ErrorBatch batch) async {
    await _load();
    _sent = batch.rev;
    await _save();
  }
}

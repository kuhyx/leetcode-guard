/// The health objects nested inside `status`. Every field is null when
/// unknown.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// Derived debt (never stored on the PC either).
class Debt {
  /// Parses a `debt` object.
  new fromJson(Json json)
    : owed = readInt(json['owed']),
      repaid = readInt(json['repaid']),
      outstanding = readInt(json['outstanding']),
      missedDays = readInt(json['missed_days']),
      summary = readString(json['summary']);

  /// Credits owed for missed days.
  final int? owed;

  /// Credits already repaid.
  final int? repaid;

  /// Still owed.
  final int? outstanding;

  /// Days missed.
  final int? missedDays;

  /// Python's one-line summary.
  final String? summary;
}

/// Ledger HMAC verification.
class Integrity {
  /// Parses an `integrity` object.
  new fromJson(Json json)
    : ok = readBool(json['ok']),
      tampered = readInt(json['tampered']),
      discounted = readInt(json['discounted']),
      unparsable = readInt(json['unparsable']),
      clockTrusted = readBool(json['clock_trusted']),
      totalEntries = readInt(json['total_entries']),
      bootstrapped = readBool(json['bootstrapped']),
      ledgerPath = readString(json['ledger_path']);

  /// Whether HMAC checking is on.
  final bool? ok;

  /// Entries whose signature failed.
  final int? tampered;

  /// Entries not counted.
  final int? discounted;

  /// Entries that did not parse.
  final int? unparsable;

  /// Whether the clock is trusted.
  final bool? clockTrusted;

  /// Ledger entries in total.
  final int? totalEntries;

  /// Whether the ledger was seeded.
  final bool? bootstrapped;

  /// Where the ledger lives on the PC.
  final String? ledgerPath;
}

/// The arming timer.
class TimerInfo {
  /// Parses a `timer` object.
  new fromJson(Json json)
    : enabled = readBool(json['enabled']),
      nextFire = readString(json['next_fire']),
      detail = readString(json['detail']);

  /// Whether it is enabled.
  final bool? enabled;

  /// When it fires next, as systemd words it.
  final String? nextFire;

  /// systemd's state word.
  final String? detail;
}

/// Clock, LeetCode auth, timer and cache health.
class Environment {
  /// Parses an `environment` object.
  new fromJson(Json json)
    : clockTrusted = readBool(json['clock_trusted']),
      authPresent = readBool(json['auth_present']),
      authNote = readString(json['auth_note']),
      poolSource = readString(json['pool_source']),
      poolNotes = readStrings(json['pool_notes']),
      cookiesConfigured = readBool(json['cookies_configured']),
      syncConfigured = readBool(json['sync_configured']),
      timer = readSection(json['timer'], TimerInfo.fromJson),
      poolCacheSummary = readString(readMap(json['pool_cache'])?['summary']),
      statementCacheSummary = readString(
        readMap(json['statement_cache'])?['summary'],
      );

  /// Whether the clock is trusted.
  final bool? clockTrusted;

  /// Whether LeetCode cookies are loaded.
  final bool? authPresent;

  /// A note on the cookies.
  final String? authNote;

  /// Where suggestions came from.
  final String? poolSource;

  /// Extra pool notes.
  final List<String>? poolNotes;

  /// Whether LeetCode cookies are configured.
  final bool? cookiesConfigured;

  /// Whether the sync token is configured.
  final bool? syncConfigured;

  /// The arming timer.
  final TimerInfo? timer;

  /// The problem-pool cache, summarised by Python.
  final String? poolCacheSummary;

  /// The offline statement cache, summarised by Python.
  final String? statementCacheSummary;
}

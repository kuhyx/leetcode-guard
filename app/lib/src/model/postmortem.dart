/// The `postmortems` section: what the tutor learned from each finished unit.
///
/// Built by the PC's `_postmortem_view` from the tutor's reports, oldest
/// unit first (DOCS-postmortem.md). Display-only, like the whole snapshot.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// `k` of `n` problems solved in one shot.
class Rate {
  /// Creates a rate.
  const new(this.k, this.n);

  /// Parses `[k, n]`; null for anything else.
  static Rate? tryParse(Object? value) {
    if (value is! List || value.length != 2) return null;
    final k = readInt(value[0]);
    final n = readInt(value[1]);
    return k == null || n == null ? null : Rate(k, n);
  }

  /// One-shot solves.
  final int k;

  /// Problems counted.
  final int n;

  /// `k / n` in 0..1, or null when nothing was counted (n == 0).
  double? get fraction => n == 0 ? null : k / n;
}

/// One problem of the unit: a row of the grid.
class PostmortemProblem {
  /// Parses a `problems[]` row.
  new fromJson(Json json)
    : slug = readString(json['slug']) ?? '',
      tries = readInt(json['tries']),
      minutes = readInt(json['minutes']),
      oneShot = readBool(json['one_shot']) ?? false,
      afterTheory = switch (json['phase']) {
        'post' => true,
        'pre' => false,
        _ => null,
      },
      finding = readString(json['finding']) ?? '';

  /// The LeetCode slug (content).
  final String slug;

  /// Failed submissions before Accepted.
  final int? tries;

  /// Minutes to Accepted; null when not measured.
  final int? minutes;

  /// Accepted on the first submission without hints.
  final bool oneShot;

  /// Solved after the unit's theory (true), before it (false), or unknown.
  final bool? afterTheory;

  /// The model's finding for this solve (content, shown after a tap).
  final String finding;
}

/// What the post-mortem did to a card. `added` is the report's `new`.
enum CardChange {
  /// A card the post-mortem wrote.
  added('new'),

  /// A card it rewrote.
  edited('edited'),

  /// A card it suspended.
  suspended('suspended'),

  /// A card it kept because one-shot solves used its idea.
  kept('kept');

  new(this.wire);

  /// The snapshot's `kind` value.
  final String wire;

  /// The change named [value], or null.
  static CardChange? parse(Object? value) {
    for (final c in values) {
      if (c.wire == value) return c;
    }
    return null;
  }
}

/// One card chip.
class PostmortemCard {
  /// Creates a chip.
  const new({
    required this.change,
    required this.front,
    required this.finding,
    required this.usedBy,
  });

  /// Parses a `cards[]` row; null for an unknown `kind`.
  static PostmortemCard? tryParse(Json json) =>
      switch (CardChange.parse(json['kind'])) {
        final CardChange change => PostmortemCard(
          change: change,
          front: readString(json['front']) ?? '',
          finding: readString(json['finding']) ?? '',
          usedBy: readStrings(json['used_by']) ?? const [],
        ),
        null => null,
      };

  /// What happened to the card.
  final CardChange change;

  /// The card's front (the new one for an edit).
  final String front;

  /// Why: the finding, the suspension reason, or a new card's `why`.
  final String finding;

  /// The one-shot solves that used a kept card's idea.
  final List<String> usedBy;
}

/// One unit's latest post-mortem revision.
class PostmortemUnit {
  /// Parses a `postmortems[]` row.
  new fromJson(Json json)
    : unit = readString(json['unit']) ?? '',
      post = Rate.tryParse(json['post']),
      pre = Rate.tryParse(json['pre']),
      problems = readObjects(json['problems'], PostmortemProblem.fromJson),
      cards = _cards(json['cards']);

  /// The unit's slug (content).
  final String unit;

  /// One-shot rate after the theory: the chart's bar.
  final Rate? post;

  /// One-shot rate before the theory.
  final Rate? pre;

  /// The grid; null when unknown (dropped to fit the snapshot).
  final List<PostmortemProblem>? problems;

  /// The chips; null when unknown.
  final List<PostmortemCard>? cards;

  static List<PostmortemCard>? _cards(Object? value) {
    final all = readObjects(value, PostmortemCard.tryParse);
    return all == null ? null : [for (final c in all) ?c];
  }
}

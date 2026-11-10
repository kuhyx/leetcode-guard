/// The "no words" guard (textgate, 2026-11-08): collects every string a
/// subtree paints and fails on any run of two ASCII letters that is not
/// named content (a problem title, a command, what the coach said, what the
/// test typed).
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fixtures.dart';

final _word = RegExp('[A-Za-z]{2,}');

/// Every painted string under [roots]: each `RichText` (every `Text` and
/// `Icon` renders one; icons are private-use glyphs, never letters), each
/// `EditableText`'s value and each field's decoration words.
List<String> paintedStrings(Iterable<Finder> roots) {
  final out = <String>[];
  for (final root in roots) {
    for (final e
        in find
            .descendant(
              of: root,
              matching: find.byType(RichText),
              matchRoot: true,
            )
            .evaluate()) {
      out.add((e.widget as RichText).text.toPlainText());
    }
    for (final e
        in find
            .descendant(of: root, matching: find.byType(EditableText))
            .evaluate()) {
      out.add((e.widget as EditableText).controller.text);
    }
    for (final e
        in find
            .descendant(of: root, matching: find.byType(TextField))
            .evaluate()) {
      final d = (e.widget as TextField).decoration;
      out.addAll([
        ?d?.hintText,
        ?d?.labelText,
        ?d?.helperText,
        ?d?.errorText,
        ?d?.counterText,
        ?d?.prefixText,
        ?d?.suffixText,
      ]);
    }
    for (final e
        in find
            .descendant(of: root, matching: find.byType(Tooltip))
            .evaluate()) {
      out.add('tooltip:${(e.widget as Tooltip).message}');
    }
  }
  return out;
}

/// The strings in [painted] that still hold a word once every [allowed]
/// content string is cut out of them.
List<String> wordsIn(Iterable<String> painted, Set<String> allowed) {
  final cuts = allowed.where((a) => a.isNotEmpty).toList()
    ..sort((a, b) => b.length.compareTo(a.length));
  return [
    for (final s in painted)
      if (_word.hasMatch(cuts.fold(s, (t, a) => t.replaceAll(a, ' ')))) s,
  ];
}

/// The overlays a screen can raise: dialogs, sheets, snack bars.
List<Finder> overlays() => [
  find.byType(Dialog),
  find.byType(BottomSheet),
  find.byType(SnackBar),
];

/// Fails unless [roots] paint something and none of it is a word outside
/// [allowed]. [where] names the screen in the failure.
void expectNoWords(
  Iterable<Finder> roots,
  Set<String> allowed, {
  required String where,
}) {
  final painted = paintedStrings(roots);
  expect(painted, isNotEmpty, reason: '$where: nothing scanned');
  expect(wordsIn(painted, allowed), isEmpty, reason: '$where paints words');
}

/// Content from a snapshot fixture's coach section: LeetCode slugs and
/// titles, and the commands kuhy types (code). Not the how-to step names,
/// command meanings or notes: those are the app's own words.
Set<String> fixtureContent(String fixture) {
  final out = <String>{};
  void walk(Object? node) {
    if (node is Map) {
      for (final MapEntry(:key, :value) in node.entries) {
        const content = {'slug', 'title', 'command', 'first_command', 'next'};
        if (content.contains(key) && value is String) out.add(value);
        walk(value);
      }
    } else if (node is List) {
      node.forEach(walk);
    }
  }

  final json = jsonDecode(fixtureText(fixture)) as Map<String, Object?>;
  walk(json['coach']);
  return out;
}

/// Finders for the coach's spoken labels (textgate: the words are no longer
/// painted, so tests find an icon, a semantics node or a numeral by what it
/// says). They read the widgets directly, so no `ensureSemantics` needed.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The label [e] speaks. An `Icon` or a `Text` builds its own `Semantics`
/// from its label: that inner node is theirs, not a second match.
String? _spoken(Element e) => switch (e.widget) {
  Icon(:final semanticLabel) => semanticLabel,
  Semantics(:final properties)
      when e.findAncestorWidgetOfExactType<Icon>() == null &&
          e.findAncestorWidgetOfExactType<Text>() == null =>
    properties.label,
  Text(:final semanticsLabel) => semanticsLabel,
  _ => null,
};

/// The widget whose spoken label is exactly [label].
Finder byLabel(String label) =>
    find.byElementPredicate((e) => _spoken(e) == label, description: label);

/// Widgets whose spoken label contains [part].
Finder byLabelContaining(String part) => find.byElementPredicate(
  (e) => _spoken(e)?.contains(part) ?? false,
  description: '~$part',
);

/// The numeral [value] painted inside the widget keyed [key].
Finder numeralIn(String key, String value) =>
    find.descendant(of: find.byKey(Key(key)), matching: find.text(value));

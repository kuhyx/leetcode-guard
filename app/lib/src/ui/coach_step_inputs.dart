/// Each step's input: free text (1, 5), a property list (2), toolbox picks
/// (3). Step 4's view is `coach_implement.dart`.
library;

import 'dart:convert';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';

/// An outlined field whose 8 KiB limit shows as a live `bytes/limit`
/// counter once the text is within a tenth of it; over the limit the
/// counter and the outline turn red (textgate: numbers, not "Too long").
InputDecoration limitDecoration(
  String text, {
  Widget? prefixIcon,
  Widget? suffix,
}) {
  final bytes = utf8.encode(text).length;
  final over = !fitsLimit(text);
  return InputDecoration(
    border: const OutlineInputBorder(),
    prefixIcon: prefixIcon,
    suffix: suffix,
    counter: bytes * 10 >= kMaxTextBytes * 9
        ? LimitCounter(bytes, over: over)
        : null,
    // An empty error widget: the red outline without any words.
    error: over ? const SizedBox.shrink() : null,
  );
}

/// `bytes/limit`, red when over.
class LimitCounter extends StatelessWidget {
  /// Creates the counter for [bytes].
  const new(this.bytes, {required this.over, super.key});

  /// UTF-8 bytes typed.
  final int bytes;

  /// Whether that is over the limit.
  final bool over;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Text(
      '$bytes/$kMaxTextBytes',
      key: const Key('limit-counter'),
      semanticsLabel: over
          ? 'Too long: $bytes of $kMaxTextBytes bytes'
          : '$bytes of $kMaxTextBytes bytes',
      style: TextStyle(color: over ? scheme.error : scheme.onSurfaceVariant),
    );
  }
}

/// Steps 1 and 5: one free-text answer.
class TextAnswerInput extends StatelessWidget {
  /// Creates the field.
  const new({
    required this.n,
    required this.field,
    required this.enabled,
    required this.onChanged,
    super.key,
  });

  /// The step.
  final int n;

  /// The draft.
  final TextEditingController field;

  /// Whether it can be edited.
  final bool enabled;

  /// Called on every edit.
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) => TextField(
    key: Key('answer-$n'),
    controller: field,
    enabled: enabled,
    minLines: 3,
    maxLines: 8,
    onChanged: (_) => onChanged(),
    decoration: limitDecoration(
      field.text,
      prefixIcon: Icon(
        stepGlyph(n).icon,
        semanticLabel: n == 1
            ? 'The rule the constraint gives you'
            : 'Why it worked',
      ),
    ),
  );
}

/// Step 2: the requirements as a list of properties, one field each. They
/// are sent newline-joined as the step's `answer`.
class PropertyListInput extends StatelessWidget {
  /// Creates the list over [fields] (grown in place by "Add property").
  const new({
    required this.fields,
    required this.enabled,
    required this.onChanged,
    super.key,
  });

  /// One draft per property.
  final List<TextEditingController> fields;

  /// Whether it can be edited.
  final bool enabled;

  /// Called on every edit and when a field is added or removed.
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final (i, field) in fields.indexed)
        Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  key: Key('property-$i'),
                  controller: field,
                  enabled: enabled,
                  onChanged: (_) => onChanged(),
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(
                      Icons.table_view,
                      semanticLabel: 'Property',
                    ),
                  ),
                ),
              ),
              if (fields.length > 1)
                IconButton(
                  key: Key('remove-property-$i'),
                  onPressed: enabled
                      ? () {
                          fields.removeAt(i).dispose();
                          onChanged();
                        }
                      : null,
                  icon: const Icon(Icons.close, semanticLabel: 'Remove'),
                ),
            ],
          ),
        ),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          key: const Key('add-property'),
          onPressed: enabled
              ? () {
                  fields.add(TextEditingController());
                  onChanged();
                }
              : null,
          icon: const Icon(Icons.add, semanticLabel: 'Add property'),
          label: const SizedBox.shrink(),
        ),
      ),
    ],
  );
}

/// Step 3: pick toolbox entries; each shows its properties.
class ToolboxInput extends StatelessWidget {
  /// Creates the list.
  const new({
    required this.entries,
    required this.picks,
    required this.enabled,
    required this.onChanged,
    super.key,
  });

  /// Every entry offered.
  final List<ToolboxEntry> entries;

  /// The picked names, changed in place.
  final Set<String> picks;

  /// Whether it can be edited.
  final bool enabled;

  /// Called on every change.
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return const Align(
        alignment: Alignment.centerLeft,
        child: Icon(
          Icons.hourglass_empty,
          semanticLabel: 'The toolbox is not loaded yet.',
        ),
      );
    }
    final full = picks.length >= kMaxPicks;
    return Column(
      children: [
        for (final e in entries)
          CheckboxListTile(
            key: Key('pick-${e.name}'),
            value: picks.contains(e.name),
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: Text(e.name),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [for (final p in e.properties) Text(p)],
            ),
            onChanged: !enabled || (full && !picks.contains(e.name))
                ? null
                : (on) {
                    on ?? false ? picks.add(e.name) : picks.remove(e.name);
                    onChanged();
                  },
          ),
      ],
    );
  }
}

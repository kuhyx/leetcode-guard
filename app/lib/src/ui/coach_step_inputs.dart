/// Each step's input: free text (1, 5), a property list (2), toolbox picks
/// (3). Step 4's view is `coach_implement.dart`.
library;

import 'dart:convert';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// "Too long" for a field over the 8 KiB limit, else null.
String? limitError(String text) {
  if (fitsLimit(text)) return null;
  return 'Too long: ${utf8.encode(text).length} of $kMaxTextBytes bytes';
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
    decoration: InputDecoration(
      border: const OutlineInputBorder(),
      hintText: n == 1 ? 'The rule the constraint gives you' : 'Why it worked',
      errorText: limitError(field.text),
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
                  decoration: InputDecoration(
                    border: const OutlineInputBorder(),
                    hintText: 'Property ${i + 1}',
                  ),
                ),
              ),
              if (fields.length > 1)
                IconButton(
                  key: Key('remove-property-$i'),
                  tooltip: 'Remove',
                  onPressed: enabled
                      ? () {
                          fields.removeAt(i).dispose();
                          onChanged();
                        }
                      : null,
                  icon: const Icon(Icons.close),
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
          icon: const Icon(Icons.add),
          label: const Text('Add property'),
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
    if (entries.isEmpty) return const Muted('The toolbox is not loaded yet.');
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

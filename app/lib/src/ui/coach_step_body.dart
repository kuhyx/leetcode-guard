/// The shown step: what it asks, its input, Submit and the last grade.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/coach_grade.dart';
import 'package:leetcode_guard/src/ui/coach_implement.dart';
import 'package:leetcode_guard/src/ui/coach_session_screen.dart';
import 'package:leetcode_guard/src/ui/coach_step_inputs.dart';
import 'package:leetcode_guard/src/ui/coach_steps.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Step [n]'s body.
class StepBody extends StatefulWidget {
  /// Creates the body.
  const new({
    required this.n,
    required this.step,
    required this.controller,
    required this.drafts,
    required this.openUrl,
    super.key,
  });

  /// 1..5.
  final int n;

  /// The relay's view of the step.
  final CoachStep step;

  /// The session controller.
  final CoachController controller;

  /// What kuhy has typed.
  final SessionDrafts drafts;

  /// Opens the problem page (step 4).
  final UrlOpener openUrl;

  @override
  State<StepBody> createState() => _StepBodyState();
}

class _StepBodyState extends State<StepBody> {
  CoachController get _c => widget.controller;
  SessionDrafts get _d => widget.drafts;

  /// Whether kuhy can still change this step's answer.
  bool get _editable => widget.step.status == StepStatus.open && _c.sid != null;

  void _changed() => setState(() {});

  String get _properties => [
    for (final p in _d.properties)
      if (p.text.trim().isNotEmpty) p.text.trim(),
  ].join('\n');

  /// The answer as it would be sent, or null when there is nothing to send.
  bool get _ready => switch (widget.n) {
    2 => _properties.isNotEmpty && fitsLimit(_properties),
    3 => _d.picks.isNotEmpty,
    _ => switch (_d.text[widget.n]?.text) {
      final String t => t.trim().isNotEmpty && fitsLimit(t),
      null => false,
    },
  };

  void _submit() {
    final n = widget.n;
    switch (n) {
      case 2:
        _c.gradeText(2, _properties);
      case 3:
        _c.gradePicks(_d.picks.toList());
      default:
        _c.gradeText(n, _d.text[n]!.text);
    }
  }

  Widget _input() => switch (widget.n) {
    2 => PropertyListInput(
      fields: _d.properties,
      enabled: _editable,
      onChanged: _changed,
    ),
    3 => ToolboxInput(
      entries: _c.state?.toolbox ?? const [],
      picks: _d.picks,
      enabled: _editable,
      onChanged: _changed,
    ),
    4 => ImplementStatus(
      step: widget.step,
      url: _c.state?.session?.url,
      openUrl: widget.openUrl,
      now: _c.now(),
    ),
    final n => TextAnswerInput(
      n: n,
      field: _d.text[n]!,
      enabled: _editable,
      onChanged: _changed,
    ),
  };

  @override
  Widget build(BuildContext context) {
    final n = widget.n;
    final showInput = _editable || n == 4;
    // A Material, not a decorated box: the toolbox's list tiles paint their
    // ink on the nearest Material.
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Material(
        color: Theme.of(context).colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.md),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Muted(kSteps[n - 1].$2),
              const SizedBox(height: AppSpacing.sm),
              if (showInput) _input(),
              if (_editable && n != 4) ...[
                const SizedBox(height: AppSpacing.sm),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton(
                    key: Key('submit-$n'),
                    onPressed: _c.canAct && _ready ? _submit : null,
                    child: const Text('Submit'),
                  ),
                ),
              ],
              if (n != 4) GradeView(n: n, step: widget.step, controller: _c),
            ],
          ),
        ),
      ),
    );
  }
}

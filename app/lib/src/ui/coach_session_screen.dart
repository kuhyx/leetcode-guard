/// One guided session: the five steps and the coach's chat.
///
/// Wide windows put the chat beside the steps; under [kSessionSplit] (the
/// shell's phone breakpoint) the two are panes of one screen. Drafts live
/// here, so switching panes or steps never loses what kuhy typed.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/coach_chat.dart';
import 'package:leetcode_guard/src/ui/coach_dialogs.dart';
import 'package:leetcode_guard/src/ui/coach_presence.dart';
import 'package:leetcode_guard/src/ui/coach_session_banners.dart';
import 'package:leetcode_guard/src/ui/coach_steps.dart';
import 'package:leetcode_guard/src/ui/coach_visible.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';

/// Below this width the chat is a pane of its own (the shell's 840 px).
const kSessionSplit = 840.0;

/// What kuhy has typed or picked, per step and in the chat.
class SessionDrafts {
  /// The free-text answers of steps 1 and 5.
  final Map<int, TextEditingController> text = {
    1: TextEditingController(),
    5: TextEditingController(),
  };

  /// Step 2's properties, one field each.
  final List<TextEditingController> properties = [TextEditingController()];

  /// Step 3's picked entry names.
  final Set<String> picks = {};

  /// The chat composer.
  final TextEditingController chat = TextEditingController();

  /// Releases the controllers.
  void dispose() {
    for (final c in [...text.values, ...properties, chat]) {
      c.dispose();
    }
  }
}

/// The session screen.
class CoachSessionScreen extends StatefulWidget {
  /// Creates the screen over [controller]; [openUrl] opens the problem.
  const new({required this.controller, required this.openUrl, super.key});

  /// The session controller.
  final CoachController controller;

  /// Opens the LeetCode page.
  final UrlOpener openUrl;

  @override
  State<CoachSessionScreen> createState() => _CoachSessionScreenState();
}

class _CoachSessionScreenState extends State<CoachSessionScreen> {
  final _drafts = SessionDrafts();
  int? _selected;
  int? _lastOpen;
  int _pane = 0;

  CoachController get _c => widget.controller;

  @override
  void dispose() {
    _drafts.dispose();
    super.dispose();
  }

  Future<void> _reveal() async {
    final yes = await confirmAction(
      context,
      action: Icons.visibility,
      semanticLabel: 'Reveal',
      confirmKey: const Key('confirm-reveal'),
      cancelKey: const Key('cancel-reveal'),
    );
    if (yes) _c.reveal();
  }

  Future<void> _end() async {
    final yes = await confirmAction(
      context,
      action: Icons.stop_circle_outlined,
      semanticLabel: 'End session',
      confirmKey: const Key('confirm-end'),
      cancelKey: const Key('cancel-end'),
    );
    if (yes) _c.endSession();
  }

  /// Follows the open step: a newly opened step becomes the one shown.
  int? _shown() {
    final open = _c.state?.step;
    if (open != _lastOpen) {
      _lastOpen = open;
      if (open != null) _selected = open;
    }
    return _selected;
  }

  Widget _steps() => StepsPanel(
    controller: _c,
    drafts: _drafts,
    selected: _shown(),
    onSelect: (n) => setState(() => _selected = n),
    openUrl: widget.openUrl,
  );

  Widget _chat() =>
      ChatPanel(controller: _c, input: _drafts.chat, onReveal: _reveal);

  Widget _body(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width >= kSessionSplit) {
      return Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: contentMaxWidth(2)),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _steps()),
              const SizedBox(width: AppSpacing.md),
              Expanded(child: _chat()),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.sm,
            AppSpacing.md,
            0,
          ),
          child: SizedBox(
            width: double.infinity,
            child: SegmentedButton<int>(
              segments: const [
                ButtonSegment(
                  value: 0,
                  icon: Icon(
                    Icons.list,
                    key: Key('steps'),
                    semanticLabel: 'Steps',
                  ),
                  label: SizedBox.shrink(),
                ),
                ButtonSegment(
                  value: 1,
                  icon: Icon(
                    Icons.chat,
                    key: Key('chat'),
                    semanticLabel: 'Chat',
                  ),
                  label: SizedBox.shrink(),
                ),
              ],
              selected: {_pane},
              showSelectedIcon: false,
              onSelectionChanged: (v) => setState(() => _pane = v.first),
            ),
          ),
        ),
        Expanded(
          child: IndexedStack(index: _pane, children: [_steps(), _chat()]),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) => CoachVisible(
    controller: _c,
    builder: (context) {
      final session = _c.state?.session;
      // The problem's own name is content; before the relay has named it
      // the bar shows the coach's glyph.
      final name = session?.title ?? session?.slug;
      return Scaffold(
        appBar: AppBar(
          // Flutter's own BackButton paints "Back" as a long-press tooltip.
          leading: IconButton(
            key: const Key('back'),
            onPressed: () => Navigator.of(context).maybePop(),
            icon: const Icon(Icons.arrow_back, semanticLabel: 'Back'),
          ),
          title: name != null
              ? Text(name)
              : const Icon(Icons.school, semanticLabel: 'Coach session'),
          actions: [
            if (_c.sid != null)
              TextButton(
                key: const Key('end-session'),
                onPressed: _c.canAct ? _end : null,
                child: const Icon(
                  Icons.stop_circle_outlined,
                  semanticLabel: 'End session',
                ),
              ),
          ],
        ),
        body: Column(
          children: [
            PresenceBanner(_c),
            SessionBanners(_c),
            Expanded(child: _body(context)),
          ],
        ),
      );
    },
  );
}

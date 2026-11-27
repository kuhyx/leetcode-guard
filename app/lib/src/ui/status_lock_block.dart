/// The PC lock on the phone: while today is unpaid, the Status tab opens on
/// the unit the lock is on and the rows it offers, each one tap from doing
/// it (a problem in LeetCode, a lesson or review in the tutor).
///
/// No words (textgate): the unit name and problem titles are content; the
/// rest is a lock, the difficulty diamonds, the review `↻` and a count.
library;

import 'package:design_system/design_system.dart';
import 'package:leetcode_guard/src/data/external_launch.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/problem_url.dart';
import 'package:leetcode_guard/src/ui/coach_grade.dart';
import 'package:leetcode_guard/src/ui/difficulty_mark.dart';
import 'package:leetcode_guard/src/ui/status_suggestions.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';
import 'package:material_ui/material_ui.dart';

/// Key of the button that opens the unit's lesson in the tutor.
const kLockLearnKey = Key('lock-learn');

/// The most of the window the block may take; past it the rows scroll, so
/// the phone's sections (the block sits above their chips) keep their room.
const kLockMaxHeightShare = 0.4;

/// The unit and rows of the lock, on a card like the sections below it.
class StatusLockBlock extends StatelessWidget {
  /// Creates the block over [lock]; [openUrl] opens every row.
  const new({required this.lock, required this.openUrl, super.key});

  /// The lock section on screen.
  final LockData lock;

  /// Hands a row's link to the OS.
  final UrlOpener openUrl;

  /// The block for [s], or none while today is paid, unknown or the
  /// snapshot predates the lock section.
  static List<Widget> header(StatusData? s, UrlOpener openUrl) => [
    if (s?.lock case final LockData lock when lock.unpaid ?? false)
      StatusLockBlock(lock: lock, openUrl: openUrl),
  ];

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final learn = tutorUri(lock.learnRoute);
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * kLockMaxHeightShare,
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(
                  Icons.lock,
                  color: statusColors(context).danger,
                  semanticLabel: 'Locked',
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Text(
                    lock.unit ?? '',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (learn != null)
                  _LearnButton(
                    key: kLockLearnKey,
                    target: learn,
                    openUrl: openUrl,
                  ),
              ],
            ),
            for (final (i, row) in (lock.rows ?? const <LockRow>[]).indexed)
              _LockRowTile(key: Key('lock-row-$i'), row: row, openUrl: openUrl),
          ],
        ),
      ),
    );
  }
}

/// A link no app took (no LeetCode app and no browser on a focus-locked
/// phone): the tap must show it failed, never do nothing.
mixin _OpensLinks<T extends StatefulWidget> on State<T> {
  bool failed = false;

  Future<void> open(UrlOpener openUrl, Uri target) async {
    final ok = await openUrl(target);
    if (mounted && ok == failed) setState(() => failed = !ok);
  }
}

Widget _failedMark(BuildContext context) => Icon(
  Icons.link_off,
  size: 20,
  color: statusColors(context).danger,
  semanticLabel: 'Unavailable',
);

class _LearnButton extends StatefulWidget {
  const new({required this.target, required this.openUrl, super.key});

  final Uri target;
  final UrlOpener openUrl;

  @override
  State<_LearnButton> createState() => _LearnButtonState();
}

class _LearnButtonState extends State<_LearnButton> with _OpensLinks {
  @override
  Widget build(BuildContext context) => IconButton(
    icon: failed
        ? _failedMark(context)
        : Icon(
            Icons.school,
            color: Theme.of(context).colorScheme.primary,
            semanticLabel: 'Tutor',
          ),
    onPressed: () => open(widget.openUrl, widget.target),
  );
}

class _LockRowTile extends StatefulWidget {
  const new({required this.row, required this.openUrl, super.key});

  final LockRow row;
  final UrlOpener openUrl;

  @override
  State<_LockRowTile> createState() => _LockRowTileState();
}

class _LockRowTileState extends State<_LockRowTile> with _OpensLinks {
  LockRow get row => widget.row;

  /// Where a tap goes: only a LeetCode problem page or a tutor route.
  Uri? get _target => switch (row) {
    LockProblem(:final url?) when isProblemUrl(url) => Uri.parse(url),
    LockProblem() => null,
    LockReview(:final route) => tutorUri(route),
  };

  @override
  Widget build(BuildContext context) {
    final target = _target;
    final scheme = Theme.of(context).colorScheme;
    final muted = scheme.onSurfaceVariant;
    return InkWell(
      borderRadius: BorderRadius.circular(AppRadius.sm),
      onTap: target == null ? null : () => open(widget.openUrl, target),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          children: [
            ...switch (row) {
              LockProblem(:final title, :final difficulty) => [
                SizedBox(
                  width: AppSpacing.md * 4,
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: DifficultyMark(difficulty ?? ''),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    show(title),
                    style: TextStyle(
                      color: target == null ? null : scheme.primary,
                    ),
                  ),
                ),
              ],
              LockReview(:final count) => [
                GlyphCount(
                  Icons.refresh,
                  show(count),
                  semanticLabel: 'Cards due',
                  color: scheme.primary,
                ),
                const Spacer(),
              ],
            },
            if (target != null && failed)
              _failedMark(context)
            else if (target != null)
              Icon(Icons.open_in_new, size: 20, color: muted),
          ],
        ),
      ),
    );
  }
}

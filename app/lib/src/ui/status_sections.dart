/// The gate sections of the Status tab: verdict and credits. Solves, days
/// and budgets live in `status_days.dart`, the diagnostic ones in
/// `status_health.dart`.
///
/// Colour is load-bearing, as in the tkinter window it replaces: red means
/// the gate is holding you, amber needs attention, green is clear. Every
/// sentence of rules (pricing, "why it did not trigger") is Python's own
/// text from the snapshot: nothing here re-derives a rule. No words are
/// painted (textgate): those sentences are spoken, and only their dates and
/// numbers are drawn, next to an icon.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/more_sheet.dart';
import 'package:leetcode_guard/src/ui/status_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The icon of each gate state Python publishes (`GateState` in
/// `leetcode_guard/_gate_state.py`); anything else is a question mark.
IconData gateStateIcon(String? state) => switch (state) {
  'not-started' => Icons.hourglass_empty,
  'already-charged' => Icons.done_all,
  'charged' => Icons.paid,
  'locked' => Icons.lock,
  'locked-clock' => Icons.update_disabled,
  'free-day' => Icons.beach_access,
  'sick-day' => Icons.sick,
  'focus-day' => Icons.center_focus_strong,
  _ => Icons.help_outline,
};

/// "Right now": am I locked, and why.
Widget verdictSection(BuildContext context, StatusData? s) {
  const title = 'Right now';
  final leading = sectionIcon(Icons.lock_clock, title);
  if (s == null) return SectionCard.unknown(title: title, leading: leading);
  final colors = statusColors(context);
  final danger = Theme.of(context).colorScheme.error;
  final reason = s.reason ?? 'Reason $kUnknown';
  final headline = switch (s.locked) {
    true => GlyphLine(
      Icons.lock,
      show(s.needed),
      spoken: 'LOCKED: solve ${show(s.needed)} more. $reason',
      color: danger,
      strong: true,
      glyphs: [Icon(Icons.code, color: danger)],
    ),
    false => GlyphLine(
      Icons.lock_open,
      '',
      spoken: 'Unlocked (${show(s.state)}). $reason',
      color: (s.available ?? 0) > 0 ? colors.success : colors.warning,
      strong: true,
      glyphs: [Icon(gateStateIcon(s.state))],
    ),
    null => GlyphLine(
      Icons.help_outline,
      kUnknown,
      spoken: 'Lock state $kUnknown. $reason',
      strong: true,
    ),
  };
  final explanation = s.explanation;
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      KeyedSubtree(key: const Key('verdict'), child: headline),
      ...iconPairs([
        InfoRow('Day', show(s.day), icon: Icons.today),
        InfoRow('Cost', show(s.cost), icon: Icons.sell_outlined),
        InfoRow('Surcharge', show(s.surcharge), icon: Icons.add_card),
        InfoRow('Paid today', show(s.chargedToday), icon: Icons.paid),
      ]),
      if (explanation != null && explanation.isNotEmpty)
        showAllButton(
          context,
          label: '',
          icon: Icons.help_outline,
          title: title,
          rows: [
            for (final (i, line) in explanation.indexed)
              spokenNote(Icons.notes, '${i + 1}. $line'),
          ],
        ),
    ],
  );
}

/// "Credits (tokens)": what you have, earned and spent.
Widget creditsSection(BuildContext context, StatusData? s) {
  const title = 'Credits (tokens)';
  final leading = sectionIcon(Icons.toll, title);
  if (s == null) return SectionCard.unknown(title: title, leading: leading);
  final colors = statusColors(context);
  final debt = s.debt;
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      GlyphLine(
        Icons.toll,
        show(s.available),
        spoken: '${show(s.available)} available',
        color: (s.available ?? 0) > 0 ? colors.success : colors.warning,
        strong: true,
        key: const Key('available'),
      ),
      ...iconPairs([
        InfoRow('Earned all-time', show(s.earnedAllTime), icon: Icons.add),
        InfoRow('Spent all-time', show(s.spentAllTime), icon: Icons.remove),
        InfoRow('Needed today', show(s.needed), icon: Icons.flag_outlined),
        if (debt == null)
          InfoRow('Debt', kUnknown, icon: Icons.money_off)
        else ...[
          InfoRow(
            'Debt outstanding',
            show(debt.outstanding),
            icon: Icons.money_off,
            color: (debt.outstanding ?? 0) > 0 ? colors.warning : null,
          ),
          InfoRow('Debt owed', show(debt.owed), icon: Icons.receipt_long),
          InfoRow('Debt repaid', show(debt.repaid), icon: Icons.replay),
          InfoRow('Missed days', show(debt.missedDays), icon: Icons.event_busy),
        ],
      ]),
      if (s.pricingNote case final String note)
        showAllButton(
          context,
          label: '',
          icon: Icons.sell_outlined,
          title: title,
          rows: [spokenNote(Icons.sell_outlined, note)],
        ),
    ],
  );
}

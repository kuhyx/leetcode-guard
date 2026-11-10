/// The diagnostic sections of the Status tab: integrity and environment.
/// The suggested problems live in `status_suggestions.dart`.
///
/// Icons, marks and numbers only (textgate): Python's notes are spoken and
/// drawn as their own dates and numbers.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/more_sheet.dart';
import 'package:leetcode_guard/src/ui/status_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

export 'package:leetcode_guard/src/ui/status_suggestions.dart';

/// "Ledger integrity": HMAC verification counts.
Widget integritySection(BuildContext context, StatusData? s) {
  const title = 'Ledger integrity';
  final leading = sectionIcon(Icons.verified_user_outlined, title);
  final i = s?.integrity;
  if (i == null) return SectionCard.unknown(title: title, leading: leading);
  final danger = Theme.of(context).colorScheme.error;
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      ...iconPairs([
        InfoRow(
          i.ok == false
              ? 'HMAC checking OFF (key unreadable)'
              : 'HMAC checking',
          show(i.ok),
          icon: i.ok == false ? Icons.key_off : Icons.key,
          color: i.ok == false ? danger : null,
          key: const Key('row-HMAC checking'),
        ),
        InfoRow(
          'Tampered',
          show(i.tampered),
          icon: Icons.gpp_bad_outlined,
          color: (i.tampered ?? 0) > 0 ? danger : null,
        ),
        InfoRow(
          'Discounted',
          show(i.discounted),
          icon: Icons.remove_circle_outline,
        ),
        InfoRow('Unparsable', show(i.unparsable), icon: Icons.broken_image),
        InfoRow('Ledger entries', show(i.totalEntries), icon: Icons.list_alt),
        InfoRow('Seeded', show(i.bootstrapped), icon: Icons.grass),
        InfoRow('Clock trusted', show(i.clockTrusted), icon: Icons.schedule),
      ]),
      // The ledger's path on the PC: data, kept as written.
      if (i.ledgerPath case final String path) Muted(path),
    ],
  );
}

/// The icon of each problem-pool source (`PoolSource` in
/// `leetcode_guard/_pool_resolve.py`), and whether it is a warning.
(IconData, bool) poolSourceIcon(String? source) => switch (source) {
  final String s when s.startsWith('live') => (
    Icons.cloud_done_outlined,
    false,
  ),
  final String s when s.startsWith('stale-cache') => (Icons.history, true),
  final String s when s.startsWith('cache') => (Icons.save_outlined, false),
  'none' => (Icons.cloud_off, true),
  _ => (Icons.help_outline, false),
};

/// "Environment": clock trust, LeetCode auth and where suggestions came from.
Widget environmentSection(BuildContext context, StatusData? s) {
  const title = 'Environment';
  final leading = sectionIcon(Icons.settings_suggest_outlined, title);
  final e = s?.environment;
  if (e == null) return SectionCard.unknown(title: title, leading: leading);
  final warning = statusColors(context).warning;
  final (poolIcon, poolWarn) = poolSourceIcon(e.poolSource);
  final nextFire = e.timer?.nextFire;
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      ...iconPairs([
        InfoRow(
          'Clock trusted',
          show(e.clockTrusted),
          icon: Icons.schedule,
          color: e.clockTrusted == false ? warning : null,
        ),
        InfoRow(
          'LeetCode cookies loaded',
          show(e.authPresent),
          icon: Icons.cookie_outlined,
          color: e.authPresent == false ? warning : null,
        ),
        InfoRow(
          'Suggestions from ${show(e.poolSource)}',
          e.poolSource == null ? kUnknown : factsOf(e.poolSource!),
          icon: poolIcon,
          color: poolWarn ? warning : null,
          key: const Key('row-Suggestions from'),
        ),
        InfoRow('Timer enabled', show(e.timer?.enabled), icon: Icons.timer),
      ]),
      // systemd's "Sat 2026-10-24 09:00:00 CEST": the date and time only.
      InfoRow(
        'Next fire ${show(nextFire)}',
        nextFire == null ? kUnknown : factsOf(nextFire),
        icon: Icons.alarm,
        key: const Key('row-Next fire'),
      ),
      showAllButton(
        context,
        label: '',
        icon: Icons.info_outline,
        title: title,
        rows: [
          if (e.authNote case final String note)
            spokenNote(Icons.cookie_outlined, note),
          ...iconPairs([
            InfoRow(
              'Cookies configured',
              show(e.cookiesConfigured),
              icon: Icons.cookie_outlined,
            ),
            InfoRow(
              'Sync token configured',
              show(e.syncConfigured),
              icon: Icons.sync,
            ),
          ]),
          spokenNote(Icons.timer, e.timer?.detail, unknownSpoken: 'Timer'),
          spokenNote(
            Icons.inventory_2_outlined,
            e.poolCacheSummary,
            unknownSpoken: 'Problem pool:',
          ),
          spokenNote(
            Icons.offline_pin_outlined,
            e.statementCacheSummary,
            unknownSpoken: 'Offline statements:',
          ),
          for (final note in e.poolNotes ?? const <String>[])
            spokenNote(Icons.notes, note),
        ],
      ),
    ],
  );
}

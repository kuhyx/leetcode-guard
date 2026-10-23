/// The diagnostic sections of the Status tab: integrity, environment and
/// the suggested problems (the app's one action).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Opens [uri] outside the app.
typedef UrlOpener = Future<bool> Function(Uri uri);

/// "Ledger integrity": HMAC verification counts.
Widget integritySection(BuildContext context, StatusData? s) {
  const title = 'Ledger integrity';
  final i = s?.integrity;
  if (i == null) return const SectionCard.unknown(title: title);
  final danger = Theme.of(context).colorScheme.error;
  return SectionCard(
    title: title,
    children: [
      InfoRow('HMAC checking', switch (i.ok) {
        true => 'on',
        false => 'OFF (key unreadable)',
        null => kUnknown,
      }, color: i.ok == false ? danger : null),
      InfoRow(
        'Tampered',
        show(i.tampered),
        color: (i.tampered ?? 0) > 0 ? danger : null,
      ),
      InfoRow('Discounted', show(i.discounted)),
      InfoRow('Unparsable', show(i.unparsable)),
      InfoRow('Ledger entries', show(i.totalEntries)),
      InfoRow('Seeded', show(i.bootstrapped)),
      InfoRow('Clock trusted', show(i.clockTrusted)),
      if (i.ledgerPath case final String path) Muted(path),
    ],
  );
}

/// "Environment": clock trust, LeetCode auth and where suggestions came from.
Widget environmentSection(BuildContext context, StatusData? s) {
  const title = 'Environment';
  final e = s?.environment;
  if (e == null) return const SectionCard.unknown(title: title);
  final warning = statusColors(context).warning;
  return SectionCard(
    title: title,
    children: [
      InfoRow(
        'Clock trusted',
        show(e.clockTrusted),
        color: e.clockTrusted == false ? warning : null,
      ),
      InfoRow(
        'LeetCode cookies loaded',
        show(e.authPresent),
        color: e.authPresent == false ? warning : null,
      ),
      if (e.authNote case final String note) Muted(note),
      InfoRow('Suggestions from', show(e.poolSource)),
      InfoRow('Cookies configured', show(e.cookiesConfigured)),
      InfoRow('Sync token configured', show(e.syncConfigured)),
      InfoRow('Timer enabled', show(e.timer?.enabled), detail: e.timer?.detail),
      InfoRow('Next fire', show(e.timer?.nextFire)),
      Muted(e.poolCacheSummary ?? 'Problem pool: $kUnknown'),
      Muted(e.statementCacheSummary ?? 'Offline statements: $kUnknown'),
      for (final note in e.poolNotes ?? const <String>[]) Muted(note),
    ],
  );
}

/// "Suggested problems": tap one to open it in the browser.
Widget suggestionsSection(StatusData? s, UrlOpener openUrl) {
  const title = 'Suggested problems';
  if (s == null) return const SectionCard.unknown(title: title);
  return SectionCard(
    title: title,
    children: listRows(
      s.suggestions,
      (item) => _SuggestionTile(item: item, openUrl: openUrl),
    ),
  );
}

class _SuggestionTile extends StatelessWidget {
  const new({required this.item, required this.openUrl});

  final Suggestion item;
  final UrlOpener openUrl;

  /// Only https opens: the URL arrives over the network, and a
  /// `javascript:` or `intent:` link must never be launched.
  Uri? get _target {
    final uri = Uri.tryParse(item.url ?? '');
    return uri != null && uri.scheme == 'https' ? uri : null;
  }

  @override
  Widget build(BuildContext context) {
    final target = _target;
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      borderRadius: BorderRadius.circular(AppRadius.sm),
      onTap: target == null ? null : () => openUrl(target),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    show(item.title),
                    style: TextStyle(
                      color: target == null ? null : scheme.primary,
                    ),
                  ),
                  Text(
                    '${show(item.difficulty)}, '
                    '${percent(item.acRate)} accepted',
                    style: TextStyle(color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            if (target != null)
              Icon(Icons.open_in_new, size: 20, color: scheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}

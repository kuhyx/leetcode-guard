/// The app shell: four tabs, the as-of time and the stale banner.
///
/// Nothing here can unlock, credit or solve: a credit exists only once
/// LeetCode confirms an accepted solve. The Coach tab's guided sessions
/// write coaching logs on the PC through its relay, and nothing else.
library;

import 'dart:async';

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show AppErrors, AppErrorsRouteObserver;
import 'package:design_system/design_system.dart';
import 'package:kuhy_credit/kuhy_credit.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/coach_live_card.dart';
import 'package:leetcode_guard/src/ui/coach_tab.dart';
import 'package:leetcode_guard/src/ui/destinations.dart';
import 'package:leetcode_guard/src/ui/postmortem_tab.dart';
import 'package:leetcode_guard/src/ui/profile_tab.dart';
import 'package:leetcode_guard/src/ui/stale_banner.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/tabs.dart';
import 'package:material_ui/material_ui.dart';

/// Width at which the bottom bar becomes a side rail (M3's medium/expanded
/// breakpoint).
const kRailBreakpoint = 840.0;

/// The root widget.
class LeetGuardApp extends StatelessWidget {
  /// Creates the app over [controller].
  const new({
    required this.controller,
    required this.openUrl,
    this.settingsBuilder,
    this.coach,
    this.lockAction,
    this.errors,
    this.debugThrow = false,
    this.navigatorKey,
    super.key,
  });

  /// Holds the snapshot.
  final StatusController controller;

  /// Opens a suggestion URL externally.
  final UrlOpener openUrl;

  /// The sync-account screen; null where the wrapper holds the credential.
  final WidgetBuilder? settingsBuilder;

  /// The guided coaching session; null leaves the Coach tab view-only.
  final CoachController? coach;

  /// The icon-only E2E passphrase button, beside the sync account; null
  /// where the wrapper holds every secret (desktop).
  final Widget? lockAction;

  /// App-wide error reporting (routes stamped into reports); null in tests.
  final AppErrors? errors;

  /// Shows an icon-only app-bar button that throws an uncaught error, to
  /// check the app-errors path on a phone. main.dart sets it only in debug
  /// builds or with `--dart-define=DEBUG_THROW=true`; releases never.
  final bool debugThrow;

  /// The navigator the in-app LeetCode view is pushed on (phone only).
  final GlobalKey<NavigatorState>? navigatorKey;

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: navigatorKey,
    // The app's proper noun, for the OS task switcher only (settled).
    title: 'LeetGuard',
    debugShowCheckedModeBanner: false,
    theme: buildDarkTheme(),
    navigatorObservers: [
      if (errors case final errors?) AppErrorsRouteObserver(errors),
    ],
    home: _Shell(this),
  );
}

class _Shell extends StatefulWidget {
  const new(this.app);

  final LeetGuardApp app;

  @override
  State<_Shell> createState() => _ShellState();
}

class _ShellState extends State<_Shell> {
  int _tab = 0;

  StatusController get _c => widget.app.controller;

  @override
  void initState() {
    super.initState();
    _c
      ..addListener(_changed)
      ..start();
  }

  @override
  void dispose() {
    _c
      ..removeListener(_changed)
      ..stop();
    super.dispose();
  }

  void _changed() => setState(() {});

  void _select(int index) => setState(() => _tab = index);

  Future<void> _openSettings(WidgetBuilder builder) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: builder,
        settings: const RouteSettings(name: '/settings'),
      ),
    );
    unawaited(_c.refresh());
  }

  Widget _body() {
    final snap = _c.snapshot;
    final generated = (snap?.generatedAt ?? _c.now()).toUtc();
    return switch (_tab) {
      0 => StatusTab(snapshot: snap, openUrl: widget.app.openUrl),
      1 => CoachTab(
        coach: snap?.coach,
        openUrl: widget.app.openUrl,
        session: switch (widget.app.coach) {
          final CoachController c => CoachSessionLink(c, widget.app.openUrl),
          null => null,
        },
      ),
      2 => ProfileTab(
        profile: snap?.profile,
        today: DateTime.utc(generated.year, generated.month, generated.day),
        now: _c.now(),
      ),
      _ => PostmortemTab(units: snap?.postmortems),
    };
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final wide = width >= kRailBreakpoint;
    final settings = widget.app.settingsBuilder;
    final content = Column(
      children: [
        if (_c.stale) StaleBanner(_c),
        Expanded(
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: contentMaxWidth(gridColumns(width)),
              ),
              child: _body(),
            ),
          ),
        ),
      ],
    );
    return Scaffold(
      appBar: AppBar(
        leading: const Padding(padding: EdgeInsets.all(8), child: KLogoSmall()),
        title: Text(
          asOf(_c.freshAt),
          style: Theme.of(context).textTheme.labelMedium
              ?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
        actions: [
          if (widget.app.debugThrow)
            IconButton(
              key: const Key('debug-throw'),
              icon: const Icon(
                Icons.bug_report_outlined,
                semanticLabel: 'Throw a test error',
              ),
              onPressed: () => throw StateError('debug throw'),
            ),
          ?widget.app.lockAction,
          if (settings != null)
            IconButton(
              icon: const Icon(
                Icons.manage_accounts_outlined,
                semanticLabel: 'Sync account',
              ),
              onPressed: () => _openSettings(settings),
            ),
          const Padding(
            padding: EdgeInsets.only(right: 12),
            child: KuhyCredit(size: 32, below: true),
          ),
        ],
      ),
      body: wide
          ? Row(
              children: [
                NavigationRail(
                  selectedIndex: _tab,
                  onDestinationSelected: _select,
                  labelType: NavigationRailLabelType.none,
                  destinations: [
                    for (final (icon, selected, label) in kDestinations)
                      NavigationRailDestination(
                        icon: Icon(icon),
                        selectedIcon: Icon(selected),
                        label: Text(label),
                      ),
                  ],
                ),
                Expanded(child: content),
              ],
            )
          : content,
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: _tab,
              onDestinationSelected: _select,
              labelBehavior: NavigationDestinationLabelBehavior.alwaysHide,
              destinations: [
                for (final (icon, selected, label) in kDestinations)
                  NavigationDestination(
                    icon: Icon(icon),
                    selectedIcon: Icon(selected),
                    label: label,
                    // An empty tooltip is none: the default paints the label
                    // on long-press.
                    tooltip: '',
                  ),
              ],
            ),
    );
  }
}

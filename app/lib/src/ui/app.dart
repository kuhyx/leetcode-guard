/// The app shell: three tabs, the as-of time and the stale banner.
///
/// Read-only by design. The only control that leaves the app is a
/// suggestion's link; there is no unlock, credit or solve action anywhere,
/// because a credit exists only once LeetCode confirms an accepted solve.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/profile_tab.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/tabs.dart';

/// Width at which the bottom bar becomes a side rail (M3's medium/expanded
/// breakpoint).
const kRailBreakpoint = 840.0;

/// Content never stretches wider than this, so a wide desktop window keeps
/// a readable line length instead of rows spanning the screen.
const kMaxContentWidth = 720.0;

/// The root widget.
class LeetGuardApp extends StatelessWidget {
  /// Creates the app over [controller].
  const new({
    required this.controller,
    required this.openUrl,
    this.settingsBuilder,
    super.key,
  });

  /// Holds the snapshot.
  final StatusController controller;

  /// Opens a suggestion URL externally.
  final UrlOpener openUrl;

  /// The sync-account screen; null where the wrapper holds the credential.
  final WidgetBuilder? settingsBuilder;

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'LeetGuard',
    debugShowCheckedModeBanner: false,
    theme: buildDarkTheme(),
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

  static const List<(IconData, String)> _destinations = [
    (Icons.shield_outlined, 'Status'),
    (Icons.school_outlined, 'Coach'),
    (Icons.person_outline, 'Profile'),
  ];

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
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: builder));
    unawaited(_c.refresh());
  }

  Widget _body() {
    final snap = _c.snapshot;
    final generated = (snap?.generatedAt ?? _c.now()).toUtc();
    return switch (_tab) {
      0 => StatusTab(snapshot: snap, openUrl: widget.app.openUrl),
      1 => CoachTab(coach: snap?.coach),
      _ => ProfileTab(
        profile: snap?.profile,
        today: DateTime.utc(generated.year, generated.month, generated.day),
        now: _c.now(),
      ),
    };
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= kRailBreakpoint;
    final settings = widget.app.settingsBuilder;
    final content = Column(
      children: [
        if (_c.stale) _StaleBanner(_c),
        Expanded(
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: kMaxContentWidth),
              child: _body(),
            ),
          ),
        ),
      ],
    );
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('LeetGuard'),
            Text(
              asOf(_c.freshAt),
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        actions: [
          if (settings != null)
            IconButton(
              tooltip: 'Sync account',
              icon: const Icon(Icons.manage_accounts_outlined),
              onPressed: () => _openSettings(settings),
            ),
        ],
      ),
      body: wide
          ? Row(
              children: [
                NavigationRail(
                  selectedIndex: _tab,
                  onDestinationSelected: _select,
                  labelType: NavigationRailLabelType.all,
                  destinations: [
                    for (final (icon, label) in _destinations)
                      NavigationRailDestination(
                        icon: Icon(icon),
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
              destinations: [
                for (final (icon, label) in _destinations)
                  NavigationDestination(icon: Icon(icon), label: label),
              ],
            ),
    );
  }
}

class _StaleBanner extends StatelessWidget {
  const new(this.c);

  final StatusController c;

  @override
  Widget build(BuildContext context) {
    final snap = c.snapshot;
    final error = c.error;
    final text = snap == null
        ? 'No snapshot yet${error == null ? '' : ': $error'}'
        : 'Stale: ${ageText(c.freshAt, c.now())}'
              '${error == null ? '' : '. Could not refresh: $error'}';
    return Container(
      key: const Key('stale-banner'),
      width: double.infinity,
      color: AppPalette.warning,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Text(text, style: const TextStyle(color: AppPalette.onFill)),
    );
  }
}

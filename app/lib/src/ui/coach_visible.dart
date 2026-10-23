/// Polls the relay only while a coach screen is on screen and the app is in
/// the foreground (`DOCS-coach-relay.md` §1: "never in the background").
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';

/// Attaches [controller] while mounted and shown; rebuilds [builder] on
/// every change.
class CoachVisible extends StatefulWidget {
  /// Creates the wrapper.
  const new({required this.controller, required this.builder, super.key});

  /// The session controller.
  final CoachController controller;

  /// The content, rebuilt whenever the controller notifies.
  final WidgetBuilder builder;

  @override
  State<CoachVisible> createState() => _CoachVisibleState();
}

class _CoachVisibleState extends State<CoachVisible> {
  late final AppLifecycleListener _lifecycle;
  bool _shown = true;

  @override
  void initState() {
    super.initState();
    widget.controller.attach();
    _lifecycle = AppLifecycleListener(onHide: _hide, onShow: _show);
  }

  void _hide() {
    if (!_shown) return;
    _shown = false;
    widget.controller.detach();
  }

  void _show() {
    if (_shown) return;
    _shown = true;
    widget.controller.attach();
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _hide();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.controller,
    builder: (context, _) => widget.builder(context),
  );
}

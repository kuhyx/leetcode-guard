/// The coach's word-free confirmation and snack bar (textgate). The
/// design system's `confirmDestructive` and `showToast` paint their labels,
/// so the coach screens use these instead.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Asks before [action] (its icon, large and in the danger hue): a cross
/// keeps things as they are, a check in the danger hue goes ahead. Escape
/// and a tap outside are "no"; the cross has focus, so a reflexive Return
/// does not confirm. [semanticLabel] is spoken, never painted.
Future<bool> confirmAction(
  BuildContext context, {
  required IconData action,
  required String semanticLabel,
  required Key confirmKey,
  required Key cancelKey,
}) async {
  final yes = await showDialog<bool>(
    context: context,
    builder: (context) {
      final danger = Theme.of(context).colorScheme.error;
      void close({required bool yes}) => Navigator.of(context).pop(yes);
      return CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.escape): () =>
              close(yes: false),
        },
        child: AlertDialog(
          icon: Icon(
            action,
            color: danger,
            size: 48,
            semanticLabel: semanticLabel,
          ),
          actionsAlignment: MainAxisAlignment.spaceBetween,
          actions: [
            IconButton(
              key: cancelKey,
              autofocus: true,
              onPressed: () => close(yes: false),
              icon: const Icon(Icons.close, semanticLabel: 'Cancel'),
            ),
            IconButton(
              key: confirmKey,
              color: danger,
              onPressed: () => close(yes: true),
              icon: Icon(Icons.check, semanticLabel: semanticLabel),
            ),
          ],
        ),
      );
    },
  );
  return yes ?? false;
}

/// A snack bar that is one icon: [icon] with [semanticLabel] spoken.
void showIconSnack(
  BuildContext context,
  IconData icon, {
  required String semanticLabel,
}) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  if (messenger == null) return;
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        duration: const Duration(seconds: 2),
        content: Align(
          alignment: Alignment.centerLeft,
          child: Icon(
            icon,
            semanticLabel: semanticLabel,
            color: Theme.of(context).colorScheme.onInverseSurface,
          ),
        ),
      ),
    );
}

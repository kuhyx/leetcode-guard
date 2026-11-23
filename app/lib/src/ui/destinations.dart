/// The shell's tabs, in navigation order.
///
/// Constants only: lcov lists no line for it, so the gate would call it
/// untested. Every entry is exercised by the shell tests.
// coverage:ignore-file
library;

import 'package:material_ui/material_ui.dart';

/// Outline icon, filled icon when selected, and the spoken name. The names
/// are never painted (textgate): the bar hides its labels, the rail keeps
/// them invisible for semantics only.
const List<(IconData, IconData, String)> kDestinations = [
  (Icons.shield_outlined, Icons.shield, 'Status'),
  (Icons.school_outlined, Icons.school, 'Coach'),
  (Icons.person_outline, Icons.person, 'Profile'),
  (Icons.fact_check_outlined, Icons.fact_check, 'Post-mortem'),
];

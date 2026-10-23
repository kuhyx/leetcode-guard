/// The device scale factor the app window opens at.
///
/// Chrome on X runs at scale 1 unless told otherwise, so on kuhy's
/// 3840x2160 panel the app rendered phone-sized text in a sea of empty
/// window. The factor is read from the output the window will open on: i3
/// maps a new window onto the focused workspace, so that workspace's output,
/// else xrandr's primary, else the first connected one. Ctrl+= / Ctrl+-
/// still adjust on top of it, and Chrome keeps that per-origin zoom in the
/// fixed profile (measured 2026-10-23 with this flag set).
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

/// `$LEETCODE_GUARD_SCALE`: a fixed factor instead of the detected one.
const kScaleEnv = 'LEETCODE_GUARD_SCALE';

/// One connected output from `xrandr --query`.
class Output {
  /// Creates an output [width] x [height] pixels.
  const new({
    required this.name,
    required this.width,
    required this.height,
    this.primary = false,
  });

  /// The RandR name (`DP-2`).
  final String name;

  /// Current mode, in pixels, as placed (rotation already applied).
  final int width;

  /// See [width].
  final int height;

  /// Whether xrandr marks it primary.
  final bool primary;
}

final _connected = RegExp(
  r'^(\S+) connected (primary )?(\d+)x(\d+)\+\d+\+\d+',
  multiLine: true,
);

/// Every connected output with a mode. One without (`connected` but off)
/// has nowhere to put a window, so it is skipped.
List<Output> parseXrandr(String query) => [
  for (final m in _connected.allMatches(query))
    Output(
      name: m[1]!,
      primary: m[2] != null,
      width: int.parse(m[3]!),
      height: int.parse(m[4]!),
    ),
];

/// The output of the focused workspace in `i3-msg -t get_workspaces`.
String? focusedOutputName(String workspacesJson) {
  final Object? decoded;
  try {
    decoded = jsonDecode(workspacesJson);
  } on FormatException {
    return null;
  }
  if (decoded is! List) return null;
  for (final ws in decoded) {
    if (ws is Map && ws['focused'] == true && ws['output'] is String) {
      return ws['output'] as String;
    }
  }
  return null;
}

/// The output a new window lands on: [focused] if xrandr lists it, else the
/// primary, else the first.
Output? pickOutput(List<Output> outputs, {String? focused}) {
  for (final o in outputs) {
    if (o.name == focused) return o;
  }
  for (final o in outputs) {
    if (o.primary) return o;
  }
  return outputs.isEmpty ? null : outputs.first;
}

/// The factor for [output]: its short side over 1080, to the nearest
/// quarter, between 1 and 3. 2160p gives 2, 1440p 1.25, 1080p and below 1.
/// The short side, so a portrait panel scales like the same panel upright.
double scaleFor(Output? output) {
  if (output == null) return 1;
  final short = math.min(output.width, output.height);
  return ((short / 1080 * 4).round() / 4).clamp(1.0, 3.0);
}

/// [raw] as a factor, or null unless it is a number in (0, 4].
double? parseScaleOverride(String? raw) {
  final value = double.tryParse(raw?.trim() ?? '');
  return value != null && value > 0 && value <= 4 ? value : null;
}

/// Runs a command, giving its stdout or null. Replaced in tests.
typedef CommandRunner = Future<String?> Function(
  String executable,
  List<String> args,
);

/// The real runner: stdout on exit 0; null on failure or a missing tool,
/// because a launcher that cannot read the screen still opens a window.
Future<String?> runQuiet(String executable, List<String> args) async {
  try {
    final result = await Process.run(executable, args);
    return result.exitCode == 0 ? result.stdout as String : null;
  } on ProcessException {
    return null;
  }
}

/// The factor the window opens at: [override] (`$LEETCODE_GUARD_SCALE`) if
/// sane, else detected from xrandr and i3, else 1.
Future<double> detectScale({
  String? override,
  CommandRunner run = runQuiet,
}) async {
  final fixed = parseScaleOverride(override ?? Platform.environment[kScaleEnv]);
  if (fixed != null) return fixed;
  final query = await run('xrandr', ['--query']);
  if (query == null) return 1;
  final workspaces = await run('i3-msg', ['-t', 'get_workspaces']);
  final focused = workspaces == null ? null : focusedOutputName(workspaces);
  return scaleFor(pickOutput(parseXrandr(query), focused: focused));
}

/// The Chrome flag for [scale]: `2`, not `2.0`.
String scaleFlag(double scale) {
  final text = scale == scale.roundToDouble()
      ? scale.toInt().toString()
      : scale.toString();
  return '--force-device-scale-factor=$text';
}

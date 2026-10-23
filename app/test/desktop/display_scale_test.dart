import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/desktop/browser.dart';
import 'package:leetcode_guard/desktop/display_scale.dart';

/// kuhy's real outputs, `xrandr --query | grep -w connected` on 2026-10-23.
const _kuhy = '''
Screen 0: minimum 8 x 8, current 6400 x 2160, maximum 32767 x 32767
DP-0 disconnected (normal left inverted right x axis y axis)
HDMI-0 connected 2560x1440+3840+0 (normal left inverted right x axis y axis) 698mm x 393mm
   2560x1440     59.95*+
DP-2 connected primary 3840x2160+0+0 (normal left inverted right x axis y axis) 620mm x 340mm
   3840x2160    143.99*+
''';

/// What Xvfb answers: one output named `screen`, not primary.
const _xvfb = '''
Screen 0: minimum 1 x 1, current 3840 x 2160, maximum 3840 x 2160
screen connected 3840x2160+0+0 0mm x 0mm
   3840x2160      0.00*
''';

const _workspaces =
    '[{"num":1,"focused":false,"output":"DP-2"},'
    '{"num":2,"focused":true,"output":"HDMI-0"}]';

void main() {
  test('parses every connected output with its geometry', () {
    final outputs = parseXrandr(_kuhy);
    expect([for (final o in outputs) o.name], ['HDMI-0', 'DP-2']);
    expect(outputs.last.primary, isTrue);
    expect(outputs.first.primary, isFalse);
    expect((outputs.last.width, outputs.last.height), (3840, 2160));
    expect(parseXrandr(_xvfb).single.name, 'screen');
  });

  test('a connected output with no mode is skipped', () {
    expect(parseXrandr('DP-4 connected (normal left inverted)\n'), isEmpty);
    expect(parseXrandr(''), isEmpty);
  });

  test('the scale follows the short side: 2 at 2160p, 1 at 1080p', () {
    double scale(int w, int h) =>
        scaleFor(Output(name: 'x', width: w, height: h));
    expect(scale(3840, 2160), 2);
    expect(scale(2560, 1440), 1.25);
    expect(scale(1920, 1080), 1);
    expect(scale(1366, 768), 1);
    expect(scale(1920, 1200), 1);
    expect(scale(2560, 1600), 1.5);
    // A portrait 4K panel is still a 4K panel.
    expect(scale(2160, 3840), 2);
    // An 8K panel stops at 3 rather than a window of four-times text.
    expect(scale(7680, 4320), 3);
    expect(scaleFor(null), 1);
  });

  test('the window opens on the focused i3 output, else the primary', () {
    final outputs = parseXrandr(_kuhy);
    expect(focusedOutputName(_workspaces), 'HDMI-0');
    expect(pickOutput(outputs, focused: 'HDMI-0')?.name, 'HDMI-0');
    expect(pickOutput(outputs)?.name, 'DP-2');
    // A focused name xrandr does not list (another X server) is ignored.
    expect(pickOutput(outputs, focused: 'DP-9')?.name, 'DP-2');
    expect(pickOutput(parseXrandr(_xvfb))?.name, 'screen');
    expect(pickOutput(const []), isNull);
  });

  test('unreadable i3 answers name no output', () {
    expect(focusedOutputName('not json'), isNull);
    expect(focusedOutputName('{"error": "x"}'), isNull);
    expect(focusedOutputName('[{"focused": false, "output": "DP-2"}]'), isNull);
    expect(focusedOutputName('[1, {"focused": true, "output": 3}]'), isNull);
  });

  test('LEETCODE_GUARD_SCALE overrides only with a sane number', () {
    expect(parseScaleOverride('1.5'), 1.5);
    expect(parseScaleOverride(' 2 '), 2);
    expect(parseScaleOverride(null), isNull);
    expect(parseScaleOverride(''), isNull);
    expect(parseScaleOverride('big'), isNull);
    expect(parseScaleOverride('0'), isNull);
    expect(parseScaleOverride('9'), isNull);
  });

  Future<String?> Function(String, List<String>) runner(
    Map<String, String?> answers,
  ) =>
      (exe, args) async => answers[exe];

  test('detectScale: 4K primary gives 2, focused 1440p output 1.25', () async {
    expect(await detectScale(run: runner({'xrandr': _kuhy})), 2);
    expect(
      await detectScale(run: runner({'xrandr': _kuhy, 'i3-msg': _workspaces})),
      1.25,
    );
  });

  test('detectScale falls back to 1 without xrandr; override wins', () async {
    expect(await detectScale(run: runner({})), 1);
    expect(
      await detectScale(override: '1.75', run: runner({'xrandr': _kuhy})),
      1.75,
    );
    expect(
      await detectScale(override: 'junk', run: runner({'xrandr': _kuhy})),
      2,
    );
  });

  test('runQuiet returns stdout, or null when the command fails', () async {
    expect(await runQuiet('echo', ['hi']), 'hi\n');
    expect(await runQuiet('false', []), isNull);
    expect(await runQuiet('/nonexistent/lg-no-such-tool', []), isNull);
  });

  test('the browser gets the factor as a plain number', () {
    expect(scaleFlag(2), '--force-device-scale-factor=2');
    expect(scaleFlag(1.25), '--force-device-scale-factor=1.25');
    expect(browserArgs('/home/k', scale: 2), contains(scaleFlag(2)));
    expect(browserArgs('/home/k').where((a) => a.contains('scale-factor')), [
      '--force-device-scale-factor=1',
    ]);
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/transport.dart';

import '../support/fake_coach_transport.dart';
import '../support/fakes.dart';

void main() {
  final clock = TestClock();
  final transport = FakeCoachTransport(clock);

  test('outages are kept for the desktop; a beat sends them', () async {
    final r = FakeReporter();
    final reporting = CoachController(
      transport: transport,
      devices: FixedDeviceId(),
      clock: clock.call,
      reporter: r,
    );
    transport.outage = const CoachUnavailable(CoachOutage.network, 'offline');
    await reporting.refresh();
    expect(r.failures, ['offline', 'offline']);
    expect(r.reaches, 0);
    transport.outage = null;
    await reporting.refresh();
    expect(r.reaches, 1);
    reporting.dispose();
  });
}

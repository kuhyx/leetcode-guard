import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A Random that always answers the top of its range.
class _Max implements Random {
  @override
  int nextInt(int max) => max - 1;

  @override
  bool nextBool() => true;

  @override
  double nextDouble() => 1;
}

void main() {
  test('id formats', () {
    expect(isUlid('01JB2Z3Y4X5W6V7T8S9R0QPNMK'), isTrue);
    expect(isUlid('01JB2Z3Y4X5W6V7T8S9R0QPNMI'), isFalse, reason: 'I');
    expect(isUlid('short'), isFalse);
    expect(isSessionId('20261023-170448-5b71'), isTrue);
    expect(isSessionId('20261023-170448-5B71'), isFalse);
    expect(isMessageKey('m0007'), isTrue);
    expect(isMessageKey('m07'), isFalse);
    expect(isSlug('missing-number'), isTrue);
    expect(isSlug('Missing'), isFalse);
    expect(isSlug('a--b'), isFalse);
    expect(isSlug('a' * 101), isFalse);
  });

  test('uuid4 is a valid device id', () {
    final id = uuid4(Random(1));
    expect(isDeviceId(id), isTrue, reason: id);
    expect(isDeviceId(uuid4(_Max())), isTrue);
    expect(isDeviceId('pc'), isFalse);
  });

  test('ULIDs are valid and sort in creation order, clock or not', () {
    var now = 1792771488000;
    final ulid = UlidGenerator(now: () => now, random: Random(7));
    final a = ulid.next();
    final b = ulid.next(); // same ms: incremented
    now -= 5; // the clock steps back
    final c = ulid.next();
    now += 100;
    final d = ulid.next();
    for (final id in [a, b, c, d]) {
      expect(isUlid(id), isTrue, reason: id);
    }
    expect([a, b, c, d], [a, b, c, d]..sort());
    expect({a, b, c, d}, hasLength(4));
    expect(isUlid(UlidGenerator().next()), isTrue);
  });

  test('the random part cannot overflow silently', () {
    final ulid = UlidGenerator(now: () => 1, random: _Max());
    expect(ulid.next(), endsWith('Z' * 16));
    expect(ulid.next, throwsStateError);
  });

  test('time outside 48 bits is refused', () {
    expect(() => encodeTime(-1), throwsArgumentError);
    expect(() => encodeTime(281474976710656), throwsArgumentError);
    expect(encodeTime(0), '0000000000');
  });

  group('PrefsDeviceId', () {
    test('creates one id and keeps it', () async {
      SharedPreferences.setMockInitialValues({});
      final store = PrefsDeviceId(random: Random(3));
      final first = await store.deviceId();
      expect(isDeviceId(first), isTrue);
      expect(await PrefsDeviceId().deviceId(), first);
    });

    test('replaces a stored value that is not a uuid4', () async {
      SharedPreferences.setMockInitialValues({PrefsDeviceId.key: 'phone'});
      final id = await PrefsDeviceId().deviceId();
      expect(id, isNot('phone'));
      expect(isDeviceId(id), isTrue);
    });
  });
}

/// The ids of the coach relay contract (`DOCS-coach-relay.md` §1, §2, §4):
/// request ids (ULID), session ids, chat keys, slugs and the per-install
/// device uuid. A path or a request is only ever built from an id that
/// passed these checks.
library;

import 'dart:math';

const _alphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

final _ulid = RegExp(r'^[0-9A-HJKMNP-TV-Z]{26}$');
final _sid = RegExp(r'^\d{8}-\d{6}-[0-9a-f]{4}$');
final _msg = RegExp(r'^m\d{4,}$');
final _slug = RegExp(r'^[a-z0-9]+(-[a-z0-9]+)*$');
final _uuid4 = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
);

/// `rid`: a 26-char Crockford ULID.
bool isUlid(String s) => _ulid.hasMatch(s);

/// Session id `YYYYMMDD-HHMMSS-xxxx` (4 hex).
bool isSessionId(String s) => _sid.hasMatch(s);

/// Chat key `m0007`.
bool isMessageKey(String s) => _msg.hasMatch(s);

/// A problem slug: `[a-z0-9]+(-[a-z0-9]+)*`, at most 100 chars.
bool isSlug(String s) => s.length <= 100 && _slug.hasMatch(s);

/// A lowercase, hyphenated uuid4 (the `dev` field).
bool isDeviceId(String s) => _uuid4.hasMatch(s);

/// A fresh uuid4 from [random].
String uuid4(Random random) {
  final bytes = List.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

// 2^48 as a literal: `1 << 48` is 0 on the web, where shifts are 32-bit
// (tutor's desktop app could not start until this was a literal).
const _timeLimit = 281474976710656;

/// Monotonic ULIDs, copied from tutor's `util/ulid.dart`: within one
/// millisecond (or after the clock steps back) the random part is
/// incremented, so one device's rids sort in creation order and the relay's
/// "rid key order" for a batch is the order kuhy pressed the buttons.
class UlidGenerator {
  /// Creates a generator; tests inject [now] (ms) and [random].
  new({int Function()? now, Random? random})
    : _now = now ?? (() => DateTime.now().millisecondsSinceEpoch),
      _random = random ?? Random.secure();

  final int Function() _now;
  final Random _random;
  int _lastTime = -1;
  List<int> _lastRandom = const [];

  /// The next id.
  String next() {
    var time = _now();
    if (time <= _lastTime) {
      time = _lastTime;
      _lastRandom = _increment(_lastRandom);
    } else {
      _lastTime = time;
      _lastRandom = List.generate(16, (_) => _random.nextInt(32));
    }
    return encodeTime(time) + _lastRandom.map((d) => _alphabet[d]).join();
  }

  static List<int> _increment(List<int> digits) {
    final out = List.of(digits);
    for (var i = out.length - 1; i >= 0; i--) {
      if (out[i] < 31) {
        out[i]++;
        return out;
      }
      out[i] = 0;
    }
    throw StateError('ULID random part overflowed within one millisecond');
  }
}

/// The 10-char time prefix of a ULID minted at [ms].
String encodeTime(int ms) {
  if (ms < 0 || ms >= _timeLimit) {
    throw ArgumentError.value(ms, 'ms', 'outside the 48-bit ULID range');
  }
  final chars = List.filled(10, '0');
  var t = ms;
  for (var i = 9; i >= 0; i--) {
    chars[i] = _alphabet[t % 32];
    t ~/= 32;
  }
  return chars.join();
}

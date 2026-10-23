/// The `dev` field of every coach request: this install's own uuid4.
///
/// Per install, never a role constant (`phone`, `pc`): two devices sharing
/// an id are indistinguishable in the relay's log. Kept in
/// `shared_preferences` (localStorage on the desktop build) because it is
/// an identity, not a secret.
library;

import 'dart:math';

import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Where the device id lives.
abstract interface class DeviceIdStore {
  /// This install's uuid4, created on first use.
  Future<String> deviceId();
}

/// [DeviceIdStore] in `shared_preferences`.
class PrefsDeviceId implements DeviceIdStore {
  /// Creates the store; [random] is injected for tests.
  new({Random? random}) : _random = random ?? Random.secure();

  /// The preferences key.
  static const key = 'coach.device_id';

  final Random _random;

  @override
  Future<String> deviceId() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(key);
    if (stored != null && isDeviceId(stored)) return stored;
    final fresh = uuid4(_random);
    await prefs.setString(key, fresh);
    return fresh;
  }
}

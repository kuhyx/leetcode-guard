import 'dart:io';

import 'package:leetcode_guard/src/model/snapshot.dart';

/// Raw text of `test/fixtures/<name>.json`.
String fixtureText(String name) =>
    File('test/fixtures/$name.json').readAsStringSync();

/// The fixture parsed, failing loudly if the parser rejects it.
Snapshot fixture(String name) => Snapshot.tryParse(fixtureText(name))!;

/// The instant every fixture was "generated" at (14:05 +02:00).
final DateTime kGeneratedAt = DateTime.parse('2026-10-23T14:05:00+02:00');

/// A clock [minutes] after [kGeneratedAt].
DateTime Function() clockAfter(int minutes) =>
    () => kGeneratedAt.add(Duration(minutes: minutes));

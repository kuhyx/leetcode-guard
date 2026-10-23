import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Every package-internal file reachable from [entry] by import or export.
Set<String> _reachable(String entry) {
  final seen = <String>{};
  final todo = [entry];
  final directive = RegExp(
    r'''^(?:import|export)\s+'([^']+)'(?:\s+if\s*\([^)]*\)\s*'([^']+)')?''',
    multiLine: true,
  );
  while (todo.isNotEmpty) {
    final path = todo.removeLast();
    if (!seen.add(path)) continue;
    for (final match in directive.allMatches(File(path).readAsStringSync())) {
      for (final uri in [match[1], match[2]].nonNulls) {
        if (uri.startsWith('package:leetcode_guard/')) {
          todo.add('lib/${uri.substring('package:leetcode_guard/'.length)}');
        } else if (!uri.contains(':')) {
          todo.add(File(path).parent.uri.resolve(uri).toFilePath());
        }
      }
    }
  }
  return seen;
}

/// The external imports of [files].
Set<String> _externalImports(Iterable<String> files) => {
  for (final file in files)
    for (final match in RegExp(
      r'''^(?:import|export)\s+'(package:[^']+|dart:[^']+)''',
      multiLine: true,
    ).allMatches(File(file).readAsStringSync()))
      if (!match[1]!.startsWith('package:leetcode_guard/')) match[1]!,
};

void main() {
  final desktop = _reachable('bin/leetcode_guard_desktop.dart');

  test('the desktop wrapper never touches the sync credential', () {
    // Desktop reads ~/.local/share/leetcode_guard/snapshot.json; Firebase
    // and ~/.config/crdt-sync/ are the phone's business only.
    final imports = _externalImports(desktop);
    expect(imports.where((i) => i.contains('crdt_sync')), isEmpty);
    expect(desktop.where((f) => f.contains('firebase')), isEmpty);
  });

  test('the wrapper runs under plain dart: no Flutter in its graph', () {
    expect(
      _externalImports(desktop).where((i) => i.startsWith('package:flutter')),
      isEmpty,
    );
  });

  test('the web app does not pull the dart:io wrapper in', () {
    final app = _reachable('lib/main.dart');
    expect(app.where((f) => f.contains('/desktop/')), isEmpty);
    expect(_externalImports(app), isNot(contains('dart:io')));
  });
}

/// Fails unless every `lib/**.dart` file is fully covered.
///
/// lcov silently omits a file no test imports, which reads as 100% while a
/// whole module is untested, so this also fails on any lib file missing from
/// the report. Files marked `coverage:ignore-file` are exempt.
///
/// Usage: `dart run tool/check_coverage.dart [coverage/lcov.info ...]`
library;

import 'dart:io';

void main(List<String> args) {
  final reports = args.isEmpty ? ['coverage/lcov.info'] : args;
  final hits = <String, Map<int, int>>{};
  for (final report in reports) {
    String? file;
    for (final line in File(report).readAsLinesSync()) {
      if (line.startsWith('SF:')) {
        // Relative (`lib/x.dart`) or absolute (`/.../app/lib/x.dart`).
        file = RegExp(r'(?:^|/)lib/(.*)$').firstMatch(line.substring(3))?[1];
      } else if (line.startsWith('DA:') && file != null) {
        final [number, count] = line.substring(3).split(',').take(2).toList();
        hits
            .putIfAbsent(file, () => {})
            .update(
              int.parse(number),
              (seen) => seen + int.parse(count),
              ifAbsent: () => int.parse(count),
            );
      }
    }
  }
  var failed = false;
  final sources = Directory('lib')
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'))
      .where((f) => !f.readAsStringSync().contains('coverage:ignore-file'));
  for (final source in sources) {
    final name = source.path.substring('lib/'.length);
    final lines = hits[name];
    if (lines == null) {
      stdout.writeln('NOT IN REPORT: lib/$name');
      failed = true;
      continue;
    }
    final missed = [
      for (final MapEntry(:key, :value) in lines.entries)
        if (value == 0) key,
    ]..sort();
    if (missed.isNotEmpty) {
      stdout.writeln('lib/$name: uncovered lines $missed');
      failed = true;
    }
  }
  final total = hits.values.fold(0, (n, l) => n + l.length);
  stdout.writeln(failed ? 'FAIL' : 'OK: 100% of $total lines in lib/');
  exitCode = failed ? 1 : 0;
}

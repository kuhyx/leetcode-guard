/// Display formatting. The one rule: null renders as "unknown", never 0.
library;

/// What every unknown value renders as.
const kUnknown = 'unknown';

/// LeetCode's difficulty keys, in the order every view lists them.
const kLevels = ['Easy', 'Medium', 'Hard'];

/// How old a snapshot may be before the app calls it stale.
const kStaleAfter = Duration(minutes: 10);

/// [value] for display: "unknown" for null, one decimal for doubles.
String show(Object? value) => switch (value) {
  null => kUnknown,
  // int first: on the web build every JSON number is a JS double, so 2 is
  // also a double there and would print as "2.0".
  final int i => '$i',
  final double d => d.toStringAsFixed(1),
  true => 'yes',
  false => 'no',
  _ => '$value',
};

/// A percentage, or "unknown".
String percent(double? value) =>
    value == null ? kUnknown : '${value.toStringAsFixed(1)}%';

/// `a / b`, or "unknown" when either side is.
String fraction(int? a, int? b) =>
    a == null || b == null ? kUnknown : '$a / $b';

/// "as of HH:MM" in the device's local time.
String asOf(DateTime? at) {
  if (at == null) return 'as of $kUnknown';
  final t = at.toLocal();
  return 'as of ${_two(t.hour)}:${_two(t.minute)}';
}

/// "as of HH:MM", with the date in front unless [at] is [now]'s day.
String asOfDated(DateTime? at, DateTime now) {
  if (at == null) return asOf(at);
  final t = at.toLocal();
  final n = now.toLocal();
  final sameDay = t.year == n.year && t.month == n.month && t.day == n.day;
  return sameDay ? asOf(t) : 'as of ${isoDate(t)} ${asOf(t).substring(6)}';
}

/// Whether a snapshot generated [at] is stale by [now]. Unknown is stale.
bool isStale(DateTime? at, DateTime now) =>
    at == null || now.difference(at) > kStaleAfter;

/// "25 min old" / "2 h old" / "age unknown".
String ageText(DateTime? at, DateTime now) {
  if (at == null) return 'age $kUnknown';
  final age = now.difference(at);
  return age.inMinutes < 120
      ? '${age.inMinutes} min old'
      : '${age.inHours} h old';
}

/// `YYYY-MM-DD` of [day].
String isoDate(DateTime day) =>
    '${day.year}-${_two(day.month)}-${_two(day.day)}';

String _two(int n) => n.toString().padLeft(2, '0');

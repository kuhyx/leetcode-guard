/// Tolerant readers for the snapshot JSON.
///
/// Every reader answers null for a missing or wrong-typed value. Null is the
/// app's "unknown", which renders as the word, never as `0`: a parser that
/// defaulted to zero would make "could not check" look like "nothing owed".
library;

/// A JSON object as a string-keyed map, or null.
typedef Json = Map<String, Object?>;

/// [value] as a [Json] object, or null.
Json? readMap(Object? value) =>
    value is Map ? value.map((k, v) => MapEntry('$k', v)) : null;

/// [value] as an int. Integral doubles count (Python may send `41.0`).
int? readInt(Object? value) {
  if (value is int) return value;
  if (value is double && value == value.truncateToDouble()) {
    return value.toInt();
  }
  return null;
}

/// [value] as a double; ints widen (Python sends `52` for 52 %).
double? readDouble(Object? value) => value is num ? value.toDouble() : null;

/// [value] as a String, or null.
String? readString(Object? value) => value is String ? value : null;

/// [value] as a bool, or null.
bool? readBool(Object? value) => value is bool ? value : null;

/// [value] parsed by [parse] when it is an object, else null (unknown).
T? readSection<T>(Object? value, T Function(Json) parse) =>
    switch (readMap(value)) {
      final Json map => parse(map),
      null => null,
    };

/// The object entries of a JSON list parsed by [parse], or null when
/// [value] is not a list. Non-object entries are skipped.
List<T>? readObjects<T>(Object? value, T Function(Json) parse) {
  if (value is! List) return null;
  return [
    for (final item in value)
      if (readMap(item) case final Json map) parse(map),
  ];
}

/// A JSON object of counts (`{"Easy": 142, ...}`); a non-integer count is
/// a null entry, a non-object is null.
Map<String, int?>? readIntMap(Object? value) =>
    readMap(value)?.map((k, v) => MapEntry(k, readInt(v)));

/// [value] as an ISO-8601 instant, or null.
DateTime? readTime(Object? value) => DateTime.tryParse(readString(value) ?? '');

/// The string entries of a JSON list, or null when it is not a list.
List<String>? readStrings(Object? value) =>
    value is List ? value.whereType<String>().toList() : null;

/// A JSON object of objects, each parsed by [parse] (a non-object value
/// becomes a null entry), or null when [value] is not an object.
Map<String, T?>? readObjectMap<T>(Object? value, T Function(Json) parse) {
  final map = readMap(value);
  if (map == null) return null;
  return {
    for (final entry in map.entries)
      entry.key: switch (readMap(entry.value)) {
        final Json m => parse(m),
        null => null,
      },
  };
}

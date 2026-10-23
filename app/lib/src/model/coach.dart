/// The `coach` section: the coaching skill's session logs.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// One coached problem.
class CoachProblem {
  /// Parses a coach problem.
  new fromJson(Json json)
    : slug = readString(json['slug']),
      cluster = readString(json['cluster']),
      reqBeforeCode = readBool(json['req_before_code']),
      maxRung = readString(json['max_rung']),
      revealed = readBool(json['revealed']),
      reqCheck = readString(json['req_check']),
      day = readString(json['day']);

  /// The problem slug.
  final String? slug;

  /// The concept cluster it belongs to.
  final String? cluster;

  /// Whether requirements were written before code.
  final bool? reqBeforeCode;

  /// The highest hint rung reached (H1...).
  final String? maxRung;

  /// Whether the solution was revealed.
  final bool? revealed;

  /// pass / incomplete / unverified.
  final String? reqCheck;

  /// The session day.
  final String? day;
}

/// A re-test that falls due.
class Retest {
  /// Parses a re-test.
  new fromJson(Json json)
    : slug = readString(json['slug']),
      due = readString(json['due']);

  /// The problem slug.
  final String? slug;

  /// When it is due.
  final String? due;
}

/// Progress through one cluster.
class ClusterProgress {
  /// Parses a cluster.
  new fromJson(Json json)
    : done = readInt(json['done']),
      total = readInt(json['total']);

  /// Problems done.
  final int? done;

  /// Problems in the cluster.
  final int? total;
}

/// The coach's session logs.
class CoachData {
  /// Parses `coach`.
  new fromJson(Json json)
    : problems = readObjects(json['problems'], CoachProblem.fromJson),
      retestsDue = readObjects(json['retests_due'], Retest.fromJson),
      clusters = readObjectMap(json['clusters'], ClusterProgress.fromJson);

  /// Coached problems. Lists: null is unknown, empty is "none".
  final List<CoachProblem>? problems;

  /// Re-tests that fall due.
  final List<Retest>? retestsDue;

  /// Cluster progress by name.
  final Map<String, ClusterProgress?>? clusters;
}

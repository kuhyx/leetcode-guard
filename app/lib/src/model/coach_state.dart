/// The relay's live-session `state` (`DOCS-coach-relay.md` §3).
///
/// Parsed tolerantly like the snapshot: a wrong-typed value is null, and
/// null is "unknown", never a default that could pass for a real answer.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// Where a step stands.
enum StepStatus {
  /// Not reachable yet: an earlier step has not passed.
  locked,

  /// The step kuhy is on.
  open,

  /// Graded pass (or, for step 4, an Accepted was seen).
  passed,

  /// Continued past after three failed tries.
  forced,

  /// A value this build does not know.
  unknown;

  /// Parses `status`.
  static StepStatus parse(Object? value) => switch (value) {
    'locked' => locked,
    'open' => open,
    'passed' => passed,
    'forced' => forced,
    _ => unknown,
  };

  /// Whether the step is behind kuhy (passed or forced).
  bool get done => this == passed || this == forced;
}

/// A step's grade.
enum Grade {
  /// Meets the bar.
  pass,

  /// Part of it.
  partial,

  /// Not yet.
  fail;

  /// Parses `grade`, or null for anything else.
  static Grade? parse(Object? value) => switch (value) {
    'pass' => pass,
    'partial' => partial,
    'fail' => fail,
    _ => null,
  };
}

/// The last grade of a step (`steps[].last`).
class StepGrade {
  /// Parses a grade object.
  new fromJson(Json json)
    : grade = Grade.parse(json['grade']),
      feedback = readString(json['feedback']),
      via = readString(json['via']),
      at = readInt(json['at']);

  /// The grade, or null when unknown.
  final Grade? grade;

  /// What is missing, as properties.
  final String? feedback;

  /// `haiku|ollama|unverified|toolbox|accepted`.
  final String? via;

  /// When, unix ms.
  final int? at;

  /// The grader was down and the step passed unchecked.
  bool get unverified => via == 'unverified';
}

/// One of the five steps.
class CoachStep {
  /// Parses a step.
  new fromJson(Json json)
    : n = readInt(json['n']),
      name = readString(json['name']),
      status = StepStatus.parse(json['status']),
      attempts = readInt(json['attempts']),
      canForce = readBool(json['can_force']) ?? false,
      last = readSection(json['last'], StepGrade.fromJson),
      probe = readString(json['probe']),
      probedAt = readInt(json['probed_at']);

  /// 1..5.
  final int? n;

  /// `constraint`, `requirements`, ...
  final String? name;

  /// Where it stands.
  final StepStatus status;

  /// Failed or partial tries so far.
  final int? attempts;

  /// Whether "Continue anyway" is offered (the relay decides).
  final bool canForce;

  /// The last grade, or null when there is none.
  final StepGrade? last;

  /// Step 4 only: `accepted|not_yet|unknown`, or null before the first probe.
  final String? probe;

  /// Step 4 only: when the probe last ran, unix ms.
  final int? probedAt;
}

/// The live (or last) session.
class SessionInfo {
  /// Parses `session`.
  new fromJson(Json json)
    : id = readString(json['id']),
      slug = readString(json['slug']),
      title = readString(json['title']),
      cluster = readString(json['cluster']),
      url = readString(json['url']),
      started = readInt(json['started']),
      ended = readInt(json['ended']),
      endReason = readString(json['end_reason']);

  /// The sid.
  final String? id;

  /// The problem slug.
  final String? slug;

  /// The problem title.
  final String? title;

  /// Its cluster.
  final String? cluster;

  /// The problem page.
  final String? url;

  /// Unix ms.
  final int? started;

  /// Unix ms, or null while live.
  final int? ended;

  /// `done|reveal|ended`.
  final String? endReason;

  /// Whether the session still takes requests.
  bool get live => ended == null && id != null;
}

/// One toolbox entry offered at step 3 (never which ones are right).
class ToolboxEntry {
  /// Parses an entry.
  new fromJson(Json json)
    : name = readString(json['name']) ?? '',
      properties = readStrings(json['properties']) ?? const [];

  /// The entry's name: what a pick sends.
  final String name;

  /// What the entry gives you.
  final List<String> properties;
}

/// The decoded `state`.
class CoachState {
  /// Parses `state`.
  new fromJson(Json json)
    : rev = readInt(json['rev']),
      step = readInt(json['step']),
      rung = readString(json['rung']),
      revealed = readBool(json['revealed']),
      session = readSection(json['session'], SessionInfo.fromJson),
      steps = readObjects(json['steps'], CoachStep.fromJson) ?? const [],
      toolbox = readObjects(json['toolbox'], ToolboxEntry.fromJson);

  /// Moves on every change (= `heartbeat.state_rev`).
  final int? rev;

  /// The open step, or null with no session.
  final int? step;

  /// The highest hint rung so far.
  final String? rung;

  /// Whether the solution was revealed.
  final bool? revealed;

  /// The session, or null when there has been none.
  final SessionInfo? session;

  /// The five steps; empty with no session.
  final List<CoachStep> steps;

  /// Present only while step 3 is open.
  final List<ToolboxEntry>? toolbox;

  /// Step [n], or null.
  CoachStep? stepAt(int n) {
    for (final s in steps) {
      if (s.n == n) return s;
    }
    return null;
  }

  /// Whether a session is live.
  bool get live => session?.live ?? false;

  /// Whether code may be sent (step 2 passed or forced).
  bool get codeOpen => stepAt(2)?.status.done ?? false;

  /// Parses an already-decoded `state`, or null when it is not an object.
  static CoachState? tryParse(Object? decoded) =>
      readSection(decoded, CoachState.fromJson);
}

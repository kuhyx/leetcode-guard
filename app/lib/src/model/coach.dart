/// The `coach` section: the coaching skill's session logs.
///
/// No sessions yet is a *known* state (empty lists, every cluster at zero,
/// `how_to` filled), so only a null section is "unknown".
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
      day = readString(json['day']),
      grades = readObjectMap(json['grades'], StepGradeSummary.fromJson),
      accepted = readBool(json['accepted']);

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

  /// The latest app session's grades by step name (`constraint`,
  /// `requirements`, `toolbox`, `postmortem`); null when unknown (a
  /// CLI-only session), a null entry when that step was never graded.
  final Map<String, StepGradeSummary?>? grades;

  /// Whether step 4 saw an Accepted in that session; null when unknown.
  final bool? accepted;
}

/// One step's grades in a past session (`coach.problems[].grades.*`).
class StepGradeSummary {
  /// Parses a summary.
  new fromJson(Json json)
    : grade = switch (json['grade']) {
        final String g when const {'pass', 'partial', 'fail'}.contains(g) => g,
        _ => null,
      },
      attempts = readInt(json['attempts']),
      forced = readBool(json['forced']),
      via = readString(json['via']);

  /// The last grade: pass / partial / fail.
  final String? grade;

  /// How many times the step was graded.
  final int? attempts;

  /// Whether kuhy continued past it.
  final bool? forced;

  /// Which grader; `unverified` means it was not checked.
  final String? via;
}

/// A re-test that falls due.
class Retest {
  /// Parses a re-test.
  new fromJson(Json json)
    : slug = readString(json['slug']),
      due = readString(json['due']),
      command = readString(json['command']);

  /// The problem slug.
  final String? slug;

  /// When it is due.
  final String? due;

  /// The shell command that starts it.
  final String? command;
}

/// One problem of a cluster, as the coach lists it.
class ClusterProblem {
  /// Parses a cluster problem.
  new fromJson(Json json)
    : slug = readString(json['slug']),
      number = readInt(json['number']),
      title = readString(json['title']),
      url = readString(json['url']);

  /// The problem slug.
  final String? slug;

  /// LeetCode's problem number.
  final int? number;

  /// The problem title, when the coach knows it.
  final String? title;

  /// The problem page.
  final String? url;
}

/// Progress through one cluster.
class ClusterProgress {
  /// Parses a cluster.
  new fromJson(Json json)
    : solved = readInt(json['solved']),
      started = readInt(json['started']),
      total = readInt(json['total']),
      order = readInt(json['order']),
      next = readString(json['next']),
      problems = readObjects(json['problems'], ClusterProblem.fromJson);

  /// Problems solved (code and post-mortem logged).
  final int? solved;

  /// Problems started (code logged).
  final int? started;

  /// Problems in the cluster.
  final int? total;

  /// Position in the curriculum: the snapshot's keys arrive sorted.
  final int? order;

  /// Slug of the first problem not started yet.
  final String? next;

  /// The cluster's problems, in curriculum order.
  final List<ClusterProblem>? problems;
}

/// One command and what it does.
class HowToCommand {
  /// Parses a command.
  new fromJson(Json json)
    : command = readString(json['command']),
      meaning = readString(json['meaning']);

  /// What to type.
  final String? command;

  /// One line on what it does.
  final String? meaning;
}

/// One step of the method.
class HowToStep {
  /// Parses a step.
  new fromJson(Json json)
    : name = readString(json['name']),
      text = readString(json['text']);

  /// The step's name.
  final String? name;

  /// One line on what to do.
  final String? text;
}

/// The commands and the four-step method, written once by the coach.
class HowTo {
  /// Parses `how_to`.
  new fromJson(Json json)
    : commands = readObjects(json['commands'], HowToCommand.fromJson),
      steps = readObjects(json['steps'], HowToStep.fromJson),
      nextNote = readString(json['next_note']),
      firstCommand = readString(json['first_command']);

  /// The commands kuhy can type.
  final List<HowToCommand>? commands;

  /// The method, in order.
  final List<HowToStep>? steps;

  /// Why "next" may differ from what the command serves.
  final String? nextNote;

  /// The command that starts the first cluster.
  final String? firstCommand;
}

/// The coach's session logs.
class CoachData {
  /// Parses `coach`.
  new fromJson(Json json)
    : problems = readObjects(json['problems'], CoachProblem.fromJson),
      retestsDue = readObjects(json['retests_due'], Retest.fromJson),
      clusters = readObjectMap(json['clusters'], ClusterProgress.fromJson),
      howTo = readSection(json['how_to'], HowTo.fromJson);

  /// Coached problems. Lists: null is unknown, empty is "none".
  final List<CoachProblem>? problems;

  /// Re-tests that fall due.
  final List<Retest>? retestsDue;

  /// Cluster progress by name.
  final Map<String, ClusterProgress?>? clusters;

  /// The commands and the method.
  final HowTo? howTo;
}

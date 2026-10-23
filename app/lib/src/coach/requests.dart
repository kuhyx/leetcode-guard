/// The seven request kinds (`DOCS-coach-relay.md` §2), with the client's
/// share of §4's limits checked before anything is sent.
library;

import 'dart:convert';

import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/ids.dart';

/// Each text field (`text`, `answer`, `code`) is at most this many UTF-8
/// bytes.
const kMaxTextBytes = 8192;

/// At most this many toolbox picks.
const kMaxPicks = 30;

/// Whether [text] is within [kMaxTextBytes].
bool fitsLimit(String text) => utf8.encode(text).length <= kMaxTextBytes;

/// The code inside [text]: the body of its first fenced block, else all.
String codeOf(String text) {
  final fenced = RegExp(r'```[^\n]*\n([\s\S]*?)```').firstMatch(text);
  return (fenced?[1] ?? text).trim();
}

/// Whether a chat message reads as code (gets "Run code"): a fence, or
/// several lines with code punctuation or keywords.
bool looksLikeCode(String text) {
  if (text.contains('```')) return true;
  return RegExp(r'[{};]|=>|\b(function|const|let|var|return)\b').hasMatch(text);
}

/// The requests a session screen sends. Each returns false (and sends
/// nothing) when an action is not allowed now or the input is out of bounds.
extension CoachRequests on CoachController {
  bool _inSession(String kind, Map<String, Object?> body, {String? runKey}) {
    final id = sid;
    if (id == null) return false;
    return send(kind, {'session': id, ...body}, runKey: runKey);
  }

  /// `session_start`.
  bool startSession(String slug) =>
      isSlug(slug) && send('session_start', {'slug': slug});

  /// `session_end`.
  bool endSession() => _inSession('session_end', {});

  /// `chat`.
  bool sendChat(String text) =>
      text.trim().isNotEmpty &&
      fitsLimit(text) &&
      _inSession('chat', {'text': text});

  /// `grade_step` for a text step (1, 2, 5).
  bool gradeText(int step, String answer) =>
      answer.trim().isNotEmpty &&
      fitsLimit(answer) &&
      _inSession('grade_step', {'step': step, 'answer': answer});

  /// `grade_step` for step 3.
  bool gradePicks(List<String> picks) =>
      picks.isNotEmpty &&
      picks.length <= kMaxPicks &&
      _inSession('grade_step', {'step': 3, 'picks': picks});

  /// `grade_step` with `force` ("Continue anyway").
  bool force(int step) =>
      _inSession('grade_step', {'step': step, 'force': true});

  /// `hint`.
  bool hint() => _inSession('hint', {});

  /// `reveal`: ends the exercise (the screen confirms first).
  bool reveal() => _inSession('reveal', {});

  /// `run_code` on chat message [key]'s code.
  bool runCode(String key, String text) {
    final code = codeOf(text);
    return code.isNotEmpty &&
        fitsLimit(code) &&
        _inSession('run_code', {'code': code}, runKey: key);
  }
}

/// Turns a network or Firebase failure into a short reason a banner can show.
///
/// 2026-10-24: the Status banner printed `ClientException.toString()`, which
/// ends in `uri=...?auth=<Firebase ID token>`, overflowing the phone by 140 px
/// and putting a live credential on screen. Every message built from a caught
/// exception goes through here, so no URL, query string or token survives:
/// the reason is one of a few fixed phrases, or the exception's type name.
///
/// No `dart:io`: the web build shares this file, so a socket failure is
/// recognised from the client's message, never by `is SocketException`.
library;

import 'dart:async';

import 'package:http/http.dart' as http;

/// No route to Firebase: DNS, refused, unreachable or reset.
const kOfflineText = "Offline: can't reach Firebase";

/// Firebase did not answer in time.
const kTimeoutText = 'Firebase timed out';

final _offline = RegExp(
  'SocketException|Failed host lookup|Connection refused|'
  'Network is unreachable|Connection reset|Connection closed|'
  'No address associated',
  caseSensitive: false,
);

final _timedOut = RegExp('timed out|TimeoutException', caseSensitive: false);

/// [error] as [kOfflineText], [kTimeoutText] or `Network error (<Type>)`.
String describeFailure(Object error) {
  if (error is TimeoutException) return kTimeoutText;
  final text = error is http.ClientException ? error.message : '$error';
  if (_offline.hasMatch(text)) return kOfflineText;
  if (_timedOut.hasMatch(text)) return kTimeoutText;
  return 'Network error (${error.runtimeType})';
}

/// A failed token refresh: the network reasons as [describeFailure], any
/// other as `Firebase sign-in failed (<Type>)`. crdt_sync wraps the refresh's
/// ClientException into its message, uri and `?key=` included.
String describeSignInFailure(Object error) {
  final text = describeFailure(error);
  return text.startsWith('Network error')
      ? 'Firebase sign-in failed (${error.runtimeType})'
      : text;
}

/// A non-2xx answer: the status code and nothing of the body.
String httpFailure(int status) => 'Firebase answered HTTP $status';

final _secrets = RegExp(
  r'[a-z][a-z0-9+.-]*://\S+|\?\S*|\b(?:auth|key|token)=\S*|'
  r'eyJ[\w-]+\.[\w-]+\.[\w-]+',
  caseSensitive: false,
);

/// [text] with every URL, query string, `auth=`/`key=`/`token=` pair and JWT
/// removed: the last line of defence before anything is shown or persisted.
String scrubSecrets(String text) => text.replaceAll(_secrets, '…');

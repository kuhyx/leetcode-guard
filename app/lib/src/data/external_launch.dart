/// Handing a link to another Android app: LeetCode problems and the tutor.
library;

import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

/// `launchUrl`'s shape, so tests can stand in for the platform.
typedef LaunchFn = Future<bool> Function(Uri uri, {LaunchMode mode});

/// A tutor route the lock may open: a lesson or a review, then one or more
/// plain path segments. The route arrives over the network, so nothing
/// else (a host, a query, a settings screen) is ever passed on.
final _tutorRoute = RegExp(r'^/(?:learn|review)(?:/[A-Za-z0-9_-]+)+$');

/// The tutor app's deep link for [route]: `/learn/s/m` becomes
/// `kuhytutor://learn/s/m`. Null for anything but a lesson or review route.
Uri? tutorUri(String? route) => route != null && _tutorRoute.hasMatch(route)
    ? Uri.parse('kuhytutor:/$route')
    : null;

/// Opens [uri] in whichever app claims it (the LeetCode app for a problem
/// if installed, else the browser; the tutor for its scheme), never inside
/// this one. False when no app does: url_launcher reports that as a
/// [PlatformException], which is an answer here, not an error.
Future<bool> openExternally(Uri uri, {LaunchFn launch = launchUrl}) async {
  try {
    return await launch(uri, mode: LaunchMode.externalApplication);
  } on PlatformException {
    return false;
  }
}

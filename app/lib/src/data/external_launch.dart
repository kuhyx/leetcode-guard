/// Handing a link to another Android app: LeetCode problems and the tutor.
library;

import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

/// `launchUrl`'s shape, so tests can stand in for the platform.
typedef LaunchFn = Future<bool> Function(Uri uri, {LaunchMode mode});

/// Opens a link in one named app ([openInPackage]'s shape, for tests).
typedef ViaPackageFn = Future<bool> Function(Uri uri, String package);

/// The tutor app: the only package a `kuhytutor://` link is handed to.
const kTutorPackage = 'com.kuhy.tutor';

/// MainActivity's `view` method: ACTION_VIEW of a URL in one package.
const kOpenChannel = MethodChannel('com.kuhy.leetcode_guard/open');

/// Asks MainActivity to open [uri] in [package] only. True when it started.
Future<bool> openInPackage(Uri uri, String package) async =>
    await kOpenChannel.invokeMethod<bool>('view', {
      'url': uri.toString(),
      'package': package,
    }) ??
    false;

/// A tutor route the lock may open: a lesson or a review, then one or more
/// plain path segments. The route arrives over the network, so nothing
/// else (a host, a query, a settings screen) is ever passed on.
final _tutorRoute = RegExp(r'^/(?:learn|review)(?:/[A-Za-z0-9_-]+)+$');

/// The tutor app's deep link for [route]: `/learn/s/m` becomes
/// `kuhytutor://learn/s/m`. Null for anything but a lesson or review route.
Uri? tutorUri(String? route) => route != null && _tutorRoute.hasMatch(route)
    ? Uri.parse('kuhytutor:/$route')
    : null;

/// Opens [uri] outside this app: a problem in whichever app claims it (the
/// LeetCode app if installed, else the browser); a tutor link in the tutor
/// only, so a test build of the tutor (a phone slot claims the same scheme)
/// never puts a chooser in front of it. False when no app takes it: that
/// arrives as a [PlatformException] (or no channel, off Android), which is
/// an answer here, not an error.
Future<bool> openExternally(
  Uri uri, {
  LaunchFn launch = launchUrl,
  ViaPackageFn viaPackage = openInPackage,
}) async {
  try {
    return uri.scheme == 'kuhytutor'
        ? await viaPackage(uri, kTutorPackage)
        : await launch(uri, mode: LaunchMode.externalApplication);
  } on PlatformException {
    return false;
  } on MissingPluginException {
    return false;
  }
}

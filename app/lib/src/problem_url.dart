/// The only kind of URL the desktop app may hand to the system browser.
library;

/// `https://leetcode.com/problems/<slug>/`, exactly: lowercase slug words
/// joined by single hyphens, the trailing slash, nothing before or after.
///
/// Anchored on both ends and with no character class that admits `.`, `/`,
/// `?`, `#`, `@`, `:` or whitespace, so no host suffix, userinfo, port,
/// extra path, query or fragment can ride along. Dart's `$` (no multiLine)
/// matches only at the very end, so a trailing newline is refused too.
final kProblemUrl = RegExp(
  r'^https://leetcode\.com/problems/[a-z0-9]+(?:-[a-z0-9]+)*/$',
);

/// Whether [url] is a LeetCode problem page the wrapper may open.
bool isProblemUrl(String url) => kProblemUrl.hasMatch(url);

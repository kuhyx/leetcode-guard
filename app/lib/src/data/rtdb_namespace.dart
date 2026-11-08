/// The sandbox namespace for this app's own RTDB URLs.
///
/// crdt_sync prefixes only its own client's paths. This app also builds REST
/// URLs itself (status, coach relay, error report), so each of them goes
/// through [namespacedPath]: a `SYNC_NAMESPACE=sandbox/slotN` build then never
/// touches real data. Empty (the default) leaves every path byte-identical.
library;

import 'package:crdt_sync/crdt_sync.dart'
    show checkSyncNamespace, syncNamespace;

/// [namespace] (default: the `SYNC_NAMESPACE` dart-define) when it is empty or
/// `sandbox/<slot>`; anything else throws (fail closed).
String resolveNamespace(String? namespace) =>
    checkSyncNamespace(namespace ?? syncNamespace);

/// [path] under [namespace]; [path] itself when [namespace] is empty.
String namespacedPath(String namespace, String path) =>
    namespace.isEmpty ? path : '$namespace/$path';

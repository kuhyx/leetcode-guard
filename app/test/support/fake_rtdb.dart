import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/e2e_stores.dart';

/// Test-cost Argon2: the real derivation, a few milliseconds.
const kTestArgon2 = Argon2Params(memoryKiB: 8, iterations: 1, parallelism: 1);

/// The passphrase every test device holds.
const kTestPassphrase = 'test-passphrase';

/// An in-memory Realtime Database behind a [MockClient]: string leaves keyed
/// by full path, REST GET (plain and `shallow`), PUT and DELETE. Real
/// crdt_sync code (FirebaseRestClient, EncryptingStore) runs over it.
class FakeRtdb {
  /// Leaves by path, no leading slash, no `.json`.
  final leaves = <String, String>{};

  /// Every GET path, in order.
  final asked = <String>[];

  /// Paths that answer with this status instead of their value.
  final failures = <String, int>{};

  /// Paths whose request throws.
  final throws = <String, Exception>{};

  /// The HTTP client to hand a [FirebaseRestClient].
  late final http.Client http_ = MockClient(_handle);

  /// A signed-in client over this database.
  Future<FirebaseRestClient> client() async {
    final store = InMemoryCredentialStore();
    await store.save(
      FirebaseCredentials(
        idToken: 'tok',
        refreshToken: 'r',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      ),
    );
    return FirebaseRestClient(
      databaseUrl: 'https://db.example',
      auth: FirebaseTokenProvider(apiKey: 'k', store: store),
      httpClient: http_,
    );
  }

  /// [SealedStores] over this database, unlocked with [passphrase].
  SealedStores stores({
    String? passphrase = kTestPassphrase,
    StoreOpener? open,
  }) => SealedStores(
    open: open ?? client,
    unlock: (store) => openEncryptedStore(
      store: store,
      oldPrefix: kSnapshotOldPrefix,
      readPassphrase: () async => passphrase,
      params: kTestArgon2,
    ),
  );

  /// The PC's side: [text] sealed at [path] under [layout], as
  /// `leetcode_guard/_snapshot_push.py` writes it.
  Future<void> seal(String path, String text, {E2eLayout? layout}) async {
    final state = await stores().snapshot();
    final into = layout ?? kSnapshotLayout;
    final store = EncryptingStore(
      await client(),
      state!.key,
      pathPrefix: into.prefix,
      revsPath: into.revsPath,
      e2ePath: into.e2ePath,
    );
    await store.putFileText(path, text, message: 'pc');
  }

  /// [path] opened with the shared key, as the PC reads it.
  Future<String?> open(String path, {E2eLayout? layout}) async {
    final state = await stores().snapshot();
    final from = layout ?? kSnapshotLayout;
    return await EncryptingStore(
      await client(),
      state!.key,
      pathPrefix: from.prefix,
      revsPath: from.revsPath,
      e2ePath: from.e2ePath,
    ).getFileText(path);
  }

  Future<http.Response> _handle(http.Request r) async {
    final path = Uri.decodeComponent(
      r.url.path,
    ).substring(1).replaceFirst(RegExp(r'\.json$'), '');
    final thrown = throws[path];
    if (thrown != null) throw thrown;
    final status = failures[path];
    if (status != null) return http.Response('err', status);
    switch (r.method) {
      case 'PUT':
        leaves[path] = jsonDecode(r.body) as String;
        return http.Response(r.body, 200);
      case 'DELETE':
        leaves.removeWhere((k, _) => k == path || k.startsWith('$path/'));
        return http.Response('null', 200);
    }
    asked.add(path);
    final leaf = leaves[path];
    if (leaf != null) return http.Response(jsonEncode(leaf), 200);
    final tree = <String, Object?>{};
    for (final MapEntry(:key, :value) in leaves.entries) {
      if (!key.startsWith('$path/')) continue;
      final parts = key.substring(path.length + 1).split('/');
      if (r.url.queryParameters['shallow'] == 'true') {
        tree[parts.first] = true;
        continue;
      }
      var node = tree;
      for (final part in parts.take(parts.length - 1)) {
        node = node.putIfAbsent(part, () => <String, Object?>{})!
            as Map<String, Object?>;
      }
      node[parts.last] = value;
    }
    return http.Response(tree.isEmpty ? 'null' : jsonEncode(tree), 200);
  }
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/pump.dart';

void main() {
  testWidgets('tapping a suggestion opens its URL', (tester) async {
    final opened = <Uri>[];
    await pumpApp(tester, opened: opened, size: const Size(390, 9000));
    await tester.tap(find.text('Single Number III'));
    expect(opened, [
      Uri.parse('https://leetcode.com/problems/single-number-iii/'),
    ]);
    // Easy is one bar, Medium two; then the acceptance rate.
    expect(find.byIcon(Icons.signal_cellular_alt_2_bar), findsOneWidget);
    expect(find.byIcon(Icons.signal_cellular_alt_1_bar), findsOneWidget);
    expect(find.text('52.0%'), findsOneWidget);
    final semantics = tester.ensureSemantics();
    // The tile merges its title and its spoken difficulty into one node.
    expect(
      find.bySemanticsLabel(RegExp(r'Medium, 52\.0% accepted')),
      findsOneWidget,
    );
    semantics.dispose();
  });

  testWidgets('a non-https suggestion is not tappable', (tester) async {
    final opened = <Uri>[];
    await pumpApp(
      tester,
      opened: opened,
      size: const Size(390, 9000),
      answers: [
        jsonEncode({
          'generated_at': '2026-10-23T14:05:00+02:00',
          'status': {
            'suggestions': [
              {'title': 'Odd', 'url': 'javascript:x'},
              {'title': 'None'},
            ],
          },
        }),
      ],
    );
    await tester.tap(find.text('Odd'));
    await tester.tap(find.text('None'));
    expect(opened, isEmpty);
  });
}

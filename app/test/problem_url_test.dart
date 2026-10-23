import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/problem_url.dart';

void main() {
  test('accepts a canonical problem page', () {
    expect(isProblemUrl('https://leetcode.com/problems/two-sum/'), isTrue);
    expect(
      isProblemUrl('https://leetcode.com/problems/find-a-node-2-in-a-clone/'),
      isTrue,
    );
    expect(isProblemUrl('https://leetcode.com/problems/3sum/'), isTrue);
  });

  test('rejects everything else', () {
    const rejected = [
      '',
      'two-sum',
      'http://leetcode.com/problems/two-sum/',
      'https://leetcode.com/problems/two-sum',
      'https://leetcode.com/problems/two-sum/description/',
      'https://leetcode.com/problems/two-sum/?x=1',
      'https://leetcode.com/problems/two-sum/#x',
      'https://leetcode.com/problems//',
      'https://leetcode.com/problems/-two-sum/',
      'https://leetcode.com/problems/two-sum-/',
      'https://leetcode.com/problems/two--sum/',
      'https://leetcode.com/problems/Two-Sum/',
      'https://leetcode.com/problems/../',
      'https://leetcode.com/problems/%2e%2e/',
      'https://leetcode.com/problems/two_sum/',
      'https://leetcode.com/problems/two sum/',
      'https://leetcode.com/problems/two-sum/\n',
      'https://leetcode.com/problems/two-sum/ ',
      ' https://leetcode.com/problems/two-sum/',
      'https://leetcode.com.evil.com/problems/two-sum/',
      'https://evil.com/https://leetcode.com/problems/two-sum/',
      'https://user@leetcode.com/problems/two-sum/',
      'https://leetcode.com:443/problems/two-sum/',
      'https://LEETCODE.com/problems/two-sum/',
      'https://www.leetcode.com/problems/two-sum/',
      'https://leetcode.cn/problems/two-sum/',
      'javascript:alert(1)//https://leetcode.com/problems/two-sum/',
      'file:///etc/passwd',
      '--help',
    ];
    for (final url in rejected) {
      expect(isProblemUrl(url), isFalse, reason: url);
    }
  });
}

import re
src = open(r'C:\Users\berds\Desktop\AMT\frontend\js\main.js', encoding='utf-8').read()

# The 3rd occurrence of "kind === 'file'" is at position 216157
# p2 (activeCoreAgentList) is at 217150, distance = 993
# p3 (core_agents: activeCore,) is at 217981, distance from p2 = 831

# Test: does [\s\S]{0,600}? match 831 chars? NO - that's the problem!
# The window between p2 and p3 is 831 chars, but the regex only allows 600.

# Let's verify
ac_pos = 217150
ca_pos = 217981
print(f"Distance p2->p3: {ca_pos - ac_pos}")
print(f"831 > 600? {ca_pos - ac_pos > 600}")

# The fix: increase the second window from 600 to 1000
pattern_fixed = r"kind === 'file'([\s\S]{0,2000}?const activeCore = activeCoreAgentList\(\);[\s\S]{0,1000}?core_agents:\s*activeCore,)"
m = re.search(pattern_fixed, src)
print(f"Fixed pattern (600->1000) match: {bool(m)}")

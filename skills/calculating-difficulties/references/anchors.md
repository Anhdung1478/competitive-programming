# Anchors

Real Codeforces problems with their true ratings. Pass C places the problem being rated
against these, in the window `[floor, floor+600]`, widened to `[floor, floor+800]` when nothing in it is comparable.

Ratings are labels, not estimates — they come from the Codeforces API. Do not adjust one
because a problem "feels" harder.

`year` is the year the anchor's round was held. It is not decoration: a rating is fitted
from the performance of the field that competed *that year*, so an old label is stated on
an older scale and must be era-corrected before the anchor is compared against a problem
being written today. SKILL.md Pass C.1 owns that correction and its table; apply it there,
never by editing the `rating` column.

Nearly half this table is old — 78 of the 171 anchors are from 2018-2020 — so the
correction fires on most placements rather than at the margins. **Choose anchors by match
quality alone and let their years fall where they may.** Pass C.1 puts an old label onto
today's scale arithmetically, which is exactly so that you never have to avoid an old one:
blind round 6 measured a preference for recent anchors and it cost 42 points of MAE.

| id | rating | year | div | prereq | intended solution |
|---|---|---|---|---|---|
| 1221B | 1100 | 2019 | Div2 | none | A knight always lands on the opposite chessboard color, so color cell (i,j) by parity of i+j making every attack a duel. |
| 1762B | 1100 | 2022 | Div2 | none | Round each element up to the next power of two, always within the allowed doubling, so all values pairwise divide. |
| 1923B | 1100 | 2024 | Div2 | two pointers, prefix sums, sorting + greedy | Merge monsters by absolute coordinate; survivable iff for every d the total health within distance d is at most k·d. |
| 2245B | 1100 | 2026 | Div1+2 | two pointers, prefix sums, sorting + greedy | Sort the values; each pairing sacrifices its smaller element, so choose p smallest elements to sacrifice maximizing c·p minus their prefix sum. |
| 2253B | 1100 | 2026 | Div2 | none | Count maximal equal runs; the single swap adds +2 when two neighbouring runs both have length ≥2, else +1 by a local check. |
| 955A | 1100 | 2018 | Div2 | none | Compare buying now at full price against waiting until 20:00 for the 20% discount; take the cheaper ceil-division. |
| 1051A | 1200 | 2018 | Div2 | none | Count characters of each class; for each missing class, overwrite one character taken from a class that still has a spare duplicate. |
| 1099C | 1200 | 2019 | Div2 | two pointers, prefix sums, sorting + greedy | Classify each letter as mandatory, optional (may drop), or repeatable (may drop/keep/repeat), then greedily pad or trim to hit length k. |
| 1130B | 1200 | 2019 | Div2 | two pointers, prefix sums, sorting + greedy | Record both positions of each size; greedily assign the two walkers to them minimizing each step's pairwise distance sum. |
| 1140D | 1200 | 2019 | Div2 | none | Every minimal triangulation is the fan from vertex 1, so the answer is sum of i*(i+1) for i=2..n-1. |
| 1207B | 1200 | 2019 | Div2 | none | Apply every 2x2 operation whose four cells of A are all ones, then check the built matrix equals A else print -1. |
| 1257C | 1200 | 2019 | Div2 | none | Track each value's previous occurrence index; the shortest dominated subarray is one more than the minimum gap between two equal values. |
| 1355A | 1200 | 2020 | Div2 | none | Simulate the recurrence but stop early once some digit is 0, since minDigit becomes 0 and the value freezes. |
| 1541B | 1200 | 2021 | Div2 | none | Bound a_i·a_j ≤ i+j ≤ 2n, then for each i enumerate candidate values of a_j and check the resulting index against a value-to-position map. |
| 1792B | 1200 | 2023 | Div2 | two pointers, prefix sums, sorting + greedy | Greedy: all type-1 jokes first, then pair type-2 with type-3, and spend accumulated mood on the surplus plus one extra. |
| 1832C | 1200 | 2023 | Div2 | two pointers, prefix sums, sorting + greedy | The contrast telescopes along monotonic runs, so keep only the array's local extrema (direction-change points); their count plus one is the answer. |
| 1874A | 1200 | 2023 | Div1 | two pointers, prefix sums, sorting + greedy | Each player greedily swaps their minimum for the opponent's maximum; the state becomes 2-periodic, so simulate by k's parity. |
| 2019B | 1200 | 2024 | Div2 | none | Derive a formula for segment coverage at each point/gap, aggregate equal coverage values in a hashmap, and answer each query by lookup. |
| 2092C | 1200 | 2025 | Div2 | none | If all values share one parity the answer is max(a); otherwise sum(a) minus (number of odd values minus one). |
| 2119B | 1200 | 2025 | Div2 | none | Reachable iff the distance lies in [max(0, 2·max a − sum a), sum a]; compare squared values to avoid floating point. |
| 934B | 1200 | 2018 | Div2 | none | Map each digit's loop count (8→2, 0/4/6/9→1, else 0) and construct floor(k/2) eights plus one extra digit if k is odd, else -1. |
| 1059B | 1300 | 2018 | Div2 | none | Stamp every 3×3 ring whose eight target cells are all '#' onto a blank grid, then compare it with the target. |
| 1076C | 1300 | 2018 | Div2 | none | Roots of x²−dx+d=0: a solution exists iff d=0 or d≥4, giving a,b=(d±√(d²−4d))/2. |
| 1558A | 1300 | 2021 | Div1 | none | For each of the two serve splits, breaks = Alice's serves + a − 2x over feasible x; output the sorted distinct values. |
| 1667A | 1300 | 2022 | Div1 | two pointers, prefix sums, sorting + greedy | Brute-force which index keeps b=0, then greedily use the fewest multiples of a_j outward in both directions; O(n^2). |
| 1775B | 1300 | 2023 | Div2 | none | Yes iff some element's every set bit occurs at least twice overall, so dropping it from the full index set leaves the OR unchanged. |
| 1870C | 1300 | 2023 | Div1+2 | none | Bucket indices by value; sweep from k down to 1 merging each value's positions into a running min/max range, giving each color's box. |
| 2152B | 1300 | 2025 | Div1+2 | none | Transform to u=r+c, v=r-c coordinates turning the king pursuit into a closed-form Chebyshev/Manhattan case analysis for the capture turn. |
| 2160C | 1300 | 2025 | Div2 | none | Note bit i and its mirrored bit of x XOR reverse(x) are forced equal, so n must satisfy a bit-palindrome condition, checked directly. |
| 2211C1 | 1300 | 2026 | Div1+2 | none | Adjacent windows force b_j=a_j outside the middle block (n-k, k]; the free block only needs distinct values drawn from a's there. |
| 919C | 1300 | 2018 | Div2 | none | Add max(L-k+1,0) over every maximal empty run in each row and column; for k=1 count each empty cell only once. |
| 946C | 1300 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | Greedy left-to-right: whenever s[i] is at most the next needed letter, raise it to that letter and advance the alphabet pointer. |
| 962B | 1300 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | Per maximal empty segment of length L, alternate seats giving ceil(L/2) to whichever group has more students left, capped by remaining counts. |
| 1004C | 1400 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | Count pairs with first(p) < last(q) by summing suffix distinct-value counts taken at each value's first occurrence. |
| 1463B | 1400 | 2020 | Div2 | none | Two candidates keep a at odd or at even indices and 1 elsewhere; their errors sum to S, so print the cheaper. |
| 1513B | 1400 | 2021 | Div2 | none | Prove prefix and suffix AND must both equal the array's overall AND X; answer is c(c-1)(n-2)! for c = frequency of X, else 0. |
| 1989C | 1400 | 2024 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Classify reviewers into nine outcome types, resolve the unambiguous ones directly, then binary-search the achievable minimum rating checking feasibility with the flexible ones. |
| 1993C | 1400 | 2024 | Div2 | two pointers, prefix sums, sorting + greedy | States repeat with period 2k: difference-array all on-intervals across the 2k window starting at max(a_i) and take the first minute counting n. |
| 2084C | 1400 | 2025 | Div1+2 | none | Columns move as units, so solvable iff the map a_i to b_i is an involution whose fixed-point count matches n's parity; realize by cycle swaps. |
| 2111D | 1400 | 2025 | Div2 | two pointers, prefix sums, sorting + greedy | Sort by floor; give min(n, m-n) groups a smallest-with-largest room pair alternated over the six slots, and park the rest in one room. |
| 2127C | 1400 | 2025 | Div1+2 | two pointers, prefix sums, sorting + greedy | Realize k rounds are irrelevant since repeating one pair suffices; sort interval endpoints to find the pair minimizing forced rearrangement cost. |
| 2164C | 1400 | 2025 | Div1+2 | two pointers, prefix sums, sorting + greedy | Kill every c>0 monster in ascending b with the weakest sufficient sword from a multiset (upgrading it), then greedily match leftovers to c=0 monsters. |
| 2245C | 1400 | 2026 | Div1+2 | none | Exploit that prefix mex is non-decreasing; greedily interleave "next missing value" and "largest unused value" insertions to hit the target XOR k. |
| 1012A | 1500 | 2018 | Div1 | two pointers, prefix sums, sorting + greedy | Sort the 2n values; answer is either the midpoint split or, with min and max paired, a sliding length-n window over the rest. |
| 1166C | 1500 | 2019 | Div2 | two pointers, prefix sums, sorting + greedy | Take absolute values, sort; a pair works iff larger ≤ twice smaller, so count with two pointers or binary search. |
| 1186D | 1500 | 2019 | Div2 | none | Floor every value; the floors sum to −k, so round up any k non-integer entries; parse decimals as strings. |
| 1242A | 1500 | 2019 | Div1 | none | Trial-divide n up to 1e6: answer is the prime p if n=p^k, otherwise 1 (and 1 for n=1). |
| 1299A | 1500 | 2020 | Div1 | none | f(x,y)=x&~y, so the value is a1 minus bits of others; put first the element owning the highest bit set exactly once. |
| 1313C1 | 1500 | 2020 | Div2 | none | n≤1000 allows brute force: fix the peak index, walk outward taking running minima of m, and keep the best total. |
| 1804C | 1500 | 2023 | Div1+2 | none | Use that triangular numbers mod n repeat with period at most 2n, so brute-force check every force f from 1 to min(p, 2n). |
| 1924A | 1500 | 2024 | Div1 | two pointers, prefix sums, sorting + greedy | Greedily partition s into consecutive blocks each covering all k letters; at least n full blocks means YES, else build a missing witness. |
| 2027C | 1500 | 2024 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Each index i is an edge from length a_i+i-1 to a_i+2i-2; DFS from n over the map-compressed graph, take the largest reachable node. |
| 2067C | 1500 | 2025 | Div2 | none | Answer is at most 9, so brute-force k in 0..9 and length p, testing whether n + k*(10^p - 1) contains a 7. |
| 2109C1 | 1500 | 2025 | Div2 | none | Interactive: repeated digit-sum reduction shrinks x to a few candidates; feedback from add/mul/div then identifies and rebuilds x as n. <!-- unsure --> |
| 2140C | 1500 | 2025 | Div2 | two pointers, prefix sums, sorting + greedy | Prove only one swap ever happens (Bob then ends); pick the best single swap via prefix max/min scans over parity-based value swings. |
| 1027C | 1600 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | Minimizing P²/S reduces to minimizing a/b+b/a, so sort lengths with count≥2 and compare only adjacent candidate pairs. |
| 1188A1 | 1600 | 2019 | Div1 | none | Answer YES iff no vertex has degree exactly 2; any other tree lets leaf-path operations set each edge independently. |
| 1389B | 1600 | 2020 | Div2 | two pointers, prefix sums, sorting + greedy | Enumerate the number j of left moves; score is the prefix sum to index k−2j+1 plus j times the best adjacent-pair prefix-max. |
| 1455D | 1600 | 2020 | Div2 | two pointers, prefix sums, sorting + greedy | Greedily scan left to right, swapping a_i with x whenever a_i > x and a_i breaks the sorted order built so far. |
| 1481C | 1600 | 2021 | Div2 | two pointers, prefix sums, sorting + greedy | Process painters in reverse, assigning each to a plank still needing that color, else to an already-repainted dump plank. |
| 1612D | 1600 | 2021 | Div2 | none | Euclidean descent on (a,b): at each step answer YES if x <= a and (a-x) % b == 0. |
| 1797C | 1600 | 2023 | Div2 | none | Query three well-chosen cells (Chebyshev distances) and algebraically solve the resulting max() equations to pin down the king's row and column. |
| 2182D | 1600 | 2025 | Div2 | none | Total turns S fixes each position's turn count (q+1 for the first S mod n, else q); count placements with a_i <= that count. |
| 980B | 1600 | 2018 | Div2 | none | Ad hoc construction: exploit top-bottom mirror symmetry between the two paths, placing hotels symmetrically (or blocking a full row) to force equal path counts. |
| 1073D | 1700 | 2018 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Binary search on the number of full laps around the circle; prefix sums give the spend per lap, then simulate the final partial lap. |
| 1153C | 1700 | 2019 | Div2 | two pointers, prefix sums, sorting + greedy | Force s0='(' and last=')', fill the earliest '?' as '(' to balance counts, then verify the prefix balance stays positive until the end. |
| 1228C | 1700 | 2019 | Div2 | none | Factorize x by trial division, then for each prime sum floor(n/p^i) (Legendre-style) to get its exponent, and multiply modpow results. |
| 1406C | 1700 | 2020 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Find centroids by subtree sizes; with two, move a leaf of the second centroid's side onto the first, else cut and re-add any edge. |
| 1478C | 1700 | 2021 | Div2 | two pointers, prefix sums, sorting + greedy | Since d_i = 2*sum_j max(abs(a_i),abs(a_j)), sort d descending and peel off each distinct value top-down, checking each appears exactly twice. |
| 1814B | 1700 | 2023 | Div2 | none | Brute-force the final leg length m up to ~10^5; cost is (m-1)+ceil(a/m)+ceil(b/m) since all lengthening may precede all jumps. |
| 2018C | 1700 | 2024 | Div1 | two pointers, prefix sums, sorting + greedy | DFS gets each node's depth and subtree height; a difference array over [depth, depth+height] finds the target depth maximizing kept nodes. |
| 2112D | 1700 | 2025 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Orient edges by depth parity so every vertex is a pure source or sink (n-1 pairs), then flip one edge whose leaf neighbour has degree two. |
| 2205D | 1700 | 2026 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Cool means valley-shaped, so the maximum must end up at an end: recurse on the Cartesian tree, g = min(left+g(right), right+g(left)). |
| 983A | 1700 | 2018 | Div1 | none | Divide q by gcd(p,q), then repeatedly strip g = gcd(q,b) from q (squaring b to keep it O(log log)); finite iff q becomes 1. |
| 1129A2 | 1800 | 2019 | Div1 | none | Per station cost = (cnt-1)*n + min dist to one chosen last destination; answer from s is max over stations of dist(s,i) + cost_i. <!-- unsure --> |
| 1190B | 1800 | 2019 | Div1 | two pointers, prefix sums, sorting + greedy | Sort, validate the one permitted duplicate pair, then the game is forced: first player wins iff sum(a) - n(n-1)/2 is odd. |
| 1327E | 1800 | 2020 | Div2 | none | Direct combinatorial formula per block length: count boundary vs interior placements with free-digit choices, using precomputed powers of 10 mod p. |
| 1420D | 1800 | 2020 | Div2 | two pointers, prefix sums, sorting + greedy | Sort intervals by left endpoint and sweep, counting still-open earlier lamps with a heap, adding C(count, k-1) modulo 998244353. |
| 1709C | 1800 | 2022 | Div2 | two pointers, prefix sums, sorting + greedy | Fill '?' greedily with all '(' then all ')'; the answer is unique unless swapping that boundary pair keeps every prefix balance nonnegative. |
| 1758D | 1800 | 2022 | Div2 | none | Constructive: fix D=max-min, pick n distinct integers clustered near D^2/n, then nudge two values so the sum equals D^2 exactly. |
| 1824B1 | 1800 | 2023 | Div1 | DSU, basic graph traversal with a twist, binary search on answer | Odd k gives answer 1; for k=2 linearity of expectation over edges adds s(n-s)/C(n,2) each, with subtree sizes s from one DFS. |
| 1923D | 1800 | 2024 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | For each slime, binary search the minimal same-direction prefix-sum window exceeding its size, merging growth from both sides. |
| 1995C | 1800 | 2024 | Div2 | two pointers, prefix sums, sorting + greedy | Left-to-right greedy carrying c_{i-1} squarings, adding the extra found by repeatedly squaring a_i until it reaches a_{i-1}; a 1 after a bigger value is impossible. |
| 2196C1 | 1800 | 2026 | Div1 | DSU, basic graph traversal with a twist, binary search on answer | Paths sharing a prefix occupy a contiguous lexicographic block, so binary search the 30-bit query index to uncover each vertex's out-neighbours one by one. <!-- unsure --> |
| 933A | 1800 | 2018 | Div1 | segment tree / BIT, standard DP over one dimension, shortest paths | Multi-phase one-dimensional DP (five states for pre-ones, the reversed twos run, and trailing ones) tracks the best achievable non-decreasing pattern. |
| 1063C | 1900 | 2018 | Div1 | none | Place points via an adaptive convex-hull construction so any online adversarial coloring stays linearly separable at the end. <!-- unsure --> |
| 1120A | 1900 | 2019 | Div1 | two pointers, prefix sums, sorting + greedy | Two-pointer sliding window locates the shortest segment containing b's required multiset, then greedily trims flowers so it becomes an early workpiece. |
| 1453D | 1900 | 2020 | Div2 | none | A checkpoint block of length L costs 2^(L+1)-2 expected tries; odd k is impossible, else greedily decompose k/2 into terms 2^L-1. |
| 1656D | 1900 | 2022 | Div1+2 | none | Odd k needs k divides n, even k needs 2n/k odd; with n = 2^a*m (m odd) answer min(2^(a+1), m), or -1 when m=1. |
| 1717D | 1900 | 2022 | Div2 | two pointers, prefix sums, sorting + greedy | Recognize the answer equals the prefix sum of C(n,i) for i=0..k, computed via precomputed factorials mod 1e9+7. |
| 2133D | 1900 | 2025 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Linear DP over the stack with a flag for whether the mob below was left at 1 HP to chain fall damage. |
| 2165B | 1900 | 2025 | Div1 | segment tree / BIT, standard DP over one dimension, shortest paths | Achievable iff the omitted values' total plus the largest omitted count is at most n; count those tuples with a knapsack DP. |
| 2173D | 1900 | 2025 | Div2 | two pointers, prefix sums, sorting + greedy | Total carries equal k plus popcount minus final popcount; greedily close zero gaps to merge runs, giving k+popcount-1 once merged. |
| 1080D | 2000 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | Greedy per-level consumption of a closed-form split capacity (4^i-1)/3 determines whether exactly k operations keep the diagonal path intact. |
| 1131D | 2000 | 2019 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | DSU-merge the "=" pairs, build a DAG of strict relations between components, topological longest-path labels; a cycle means No. |
| 1142B | 2000 | 2019 | Div1 | segment tree / BIT, standard DP over one dimension, shortest paths | Binary lifting over next-occurrence-of-successor pointers to jump n-1 steps, then suffix minimum of endpoints answers each query. |
| 1370D | 2000 | 2020 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Binary search the answer; greedily scan to check a length-k subsequence whose odd- (or even-) indexed elements are all <= x. |
| 1379C | 2000 | 2020 | Div2 | two pointers, prefix sums, sorting + greedy | Sort a descending with prefix sums; for each type's b_i, take every a_j > b_i then fill the remaining flowers with b_i. |
| 1380D | 2000 | 2020 | Div2 | two pointers, prefix sums, sorting + greedy | Match b as a subsequence of a, then cost each gap greedily: a fireball is forced when the gap max beats both borders. |
| 1513D | 2000 | 2021 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Process values ascending; binary-search each one's maximal gcd-equal range via sparse table, then DSU-merge that range at this weight, Kruskal-style. |
| 1867E1 | 2000 | 2023 | Div2 | none | XOR disjoint k-blocks left to right; for the even leftover one overlapping query at n-k+1 cancels the already-reversed overlap. |
| 1905D | 2000 | 2023 | Div2 | none | Keep the non-decreasing prefix-mex values in a deque of (value,count) with a running sum; rotating pops the front and clamps the back to p_1. |
| 1943B | 2000 | 2024 | Div1 | two pointers, prefix sums, sorting + greedy | Because overlapping equal-length palindromic substrings force periodicity, almost every k is good except the whole segment or its trim, verified via O(1) palindrome hashing. |
| 1987E | 2000 | 2024 | Div1+2 | DSU, basic graph traversal with a twist, binary search on answer | Slack b_v = sum of children a_u minus a_v; pulling surplus from a descendant costs its depth gap, so greedily fix deficits bottom-up. |
| 2103D | 2000 | 2025 | Div2 | two pointers, prefix sums, sorting + greedy | Assign values greedily by iteration: elements removed at odd iterations take the largest unused values, even iterations the smallest, two pointers inward. |
| 2140D | 2000 | 2025 | Div2 | two pointers, prefix sums, sorting + greedy | Each pair adds one segment's r minus the other's l; sort by l+r, top half donate r, prefix sums cover the odd leftover. |
| 1185G1 | 2100 | 2019 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Bitmask DP over the 2^15 song subsets keyed by last genre; the mask fixes elapsed time, so count orders summing to T. |
| 1187E | 2100 | 2019 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Score from a start vertex is the sum of all subtree sizes rooted there; compute one root then reroot in O(n). |
| 1265E | 2100 | 2019 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Express expected days E via a backward linear recurrence per mirror, solve the self-referential equation in E, using modular inverse. |
| 1278D | 2100 | 2019 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Sweep endpoints with a BIT-based stack to find each crossing-pair edge, then DSU-union them checking for exactly n-1 edges and no cycle. |
| 2210D | 2100 | 2026 | Div2 | none | Swaps never change which pairs are leaves, so YES iff equal "()" counts, except rigid nested-chain-around-sibling-leaves strings, which match only themselves. |
| 990E | 2100 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | For each power l greedily jump via the precomputed nearest free position; harmonic O(n log n) total, then minimize count times a_l. |
| 995A | 2100 | 2018 | Div1 | none | Rotate cars cyclically through the 2n middle cells, parking each when aligned with its spot; -1 only if the middle rows are full and nothing parks. |
| 1114E | 2200 | 2019 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Binary search with 30 ">" queries for the maximum, sample 30 random indices, take the gcd of their gaps to that maximum. |
| 1166D | 2200 | 2019 | Div2 | two pointers, prefix sums, sorting + greedy | Brute force length k up to 50: b - a*2^(k-2) must lie in [S, m*S] with S = 2^(k-1)-1, then split r greedily. |
| 1295E | 2200 | 2020 | Div2 | lazy propagation, SOS DP, matrix exponentiation, flows | Sweep the value threshold; a lazy range-add range-min segment tree over split points maintains the cost of moving mismatched elements. |
| 1428E | 2200 | 2020 | Div1+2 | two pointers, prefix sums, sorting + greedy | Priority-queue greedy: cutting a carrot into p near-equal parts has convex cost, so take the largest marginal gain k-n times. |
| 1470D | 2200 | 2021 | Div1 | DSU, basic graph traversal with a twist, binary search on answer | DFS the graph marking a vertex a teacher only if no visited neighbour is one; disconnected graphs answer NO. |
| 1695D1 | 2200 | 2022 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Compute the tree's metric dimension via leaves minus exterior-major-vertices: walk each leaf up to its nearest degree>=3 ancestor and count distinct ones. |
| 1841E | 2200 | 2023 | Div2 | two pointers, prefix sums, sorting + greedy | Monotonic-stack/Cartesian-tree split on the maximum a_i enumerates maximal free rectangles; greedily fill the widest runs first, a length-L run giving L-1 beauty. |
| 1848D | 2200 | 2023 | Div2 | none | Last digit cycles 2,4,8,6 adding 20 every four steps; for each of four offsets maximize the quadratic (s+20i)(k-i) at its vertex. |
| 1909F1 | 2200 | 2023 | Div1+2 | none | Track d_i = i - a_i as the unmatched row/column defect; multiply per-step factors 1, 1+2d, or d^2 depending on a_i - a_{i-1}. |
| 2025E | 2200 | 2024 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | DP over suits carrying how many surplus trumps player 1 must spend; each non-trump suit's split count is a ballot/Catalan number. |
| 2209E | 2200 | 2026 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Z-function of the query suffix, then DP g[i]=max{g[j]+1 : j+z[j+1]>=i}; g is monotone so a pointer finds the best j. |
| 920G | 2200 | 2018 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Binary search the answer, counting integers up to m coprime to p by inclusion-exclusion over p's distinct primes from an SPF sieve. |
| 932D | 2200 | 2018 | Div1+2 | none | Build each node's chain to its nearest ancestor with weight >= its own via binary lifting, then binary-search that chain's prefix sum against X. |
| 979D | 2200 | 2018 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Insert u into a binary trie per divisor; walk bits maximizing XOR while a tight flag keeps v within s-x. |
| 980E | 2200 | 2018 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Repeatedly pop the smallest-indexed leaf from a min-heap k times, since 2^i weighting means only leaf removals preserve the optimum. |
| 1282D | 2300 | 2019 | Div2 | none | Two length-300 all-a and all-b queries reveal n, then flipping each position once and reading edit distance fixes every character. |
| 1292C | 2300 | 2020 | Div1 | digit DP, bitmask DP over subsets, tree DP with rerooting | Optimal labels occupy one path, so dp[u][v] = max(dp[par u][v], dp[u][par v]) + size_u*size_v over all vertex pairs. |
| 1513E | 2300 | 2021 | Div2 | none | Split values into above/below/equal-average groups; require both non-equal groups contiguous (2 orderings) if size >= 2 each, else count all permutations via factorials. |
| 1594E2 | 2300 | 2021 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Six-colour tree DP over the O(nk) ancestors of the fixed nodes; each untouched subtree contributes a precomputed power 4^(2^h-1). |
| 1743F | 2300 | 2022 | Div2 | lazy propagation, SOS DP, matrix exponentiation, flows | Segment tree over coordinates with lazy 2x2 count-transition matrices: union sets the bit, intersection clears, xor flips; sum one-states. |
| 2002D2 | 2300 | 2024 | Div1+2 | none | Reduce global DFS-order validity to a local, O(1)-checkable condition per adjacent permutation pair using ancestor/subtree-size relations, updated after each swap. |
| 1107G | 2400 | 2019 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Monotonic stack fixes each gap's maximal range, then sparse-table range max/min of prefix sums of (a - c) maximises segment profit. |
| 1137D | 2400 | 2019 | Div1 | DSU, basic graph traversal with a twist, binary search on answer | Floyd tortoise-and-hare with two token groups on the rho-shaped functional graph finds the cycle, then everyone walks to finish. |
| 1239D | 2400 | 2019 | Div1 | DSU, basic graph traversal with a twist, binary search on answer | Build resident-to-resident edges from acquaintances; any sink strongly connected component smaller than n is the jury, complement cats compete. |
| 1348E | 2400 | 2020 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Limit mixed single-shrub baskets to shrubs with min(a_i,b_i) < k, then knapsack-DP over achievable red-berry totals mod basket size. |
| 1634E | 2400 | 2022 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Bipartite multigraph of arrays versus values has all degrees even, so an Euler circuit orients every element into L or R. |
| 1735E | 2400 | 2022 | Div2 | two pointers, prefix sums, sorting + greedy | Enumerate O(n) candidate values for the distance between p1 and p2 from the largest d1 entry, then greedily match distances with multisets. |
| 1860E | 2400 | 2023 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Compress positions by adjacent-letter-pair class, precompute nearest-class distances, run Floyd-Warshall over the <=676 classes, then combine per query. |
| 1886E | 2400 | 2023 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Sort tolerances descending; bitmask DP over project subsets storing the shortest prefix consumed, each project taking a contiguous block sized by binary search. |
| 1981D | 2400 | 2024 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | Map values to primes and adjacent pairs to edges; find the smallest k whose loop-complete graph admits an Eulerian trail of n-1 edges. |
| 1993F1 | 2400 | 2024 | Div2 | two pointers, prefix sums, sorting + greedy | Unfold the reflections: the robot sits at origin iff prefix displacement is 0 mod 2w and 2h; hash-count prefixes per repetition offset. |
| 2005D | 2400 | 2024 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Precompute prefix/suffix gcds; for each l, jump through the O(log) breakpoints where the swapped-range gcds change, maximizing the sum. |
| 2097C | 2400 | 2025 | Div1 | none | Unfold the triangle via repeated reflections into a straight line, then use gcd/Euclidean analysis on velocity ratios to find escape vertex and bounce count. |
| 2169E | 2400 | 2025 | Div2 | two pointers, prefix sums, sorting + greedy | Optimal remaining set is the at-most-four extreme points; enumerate which roles share a point and take top candidates per linear objective. |
| 939F | 2400 | 2018 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | DP over flip intervals keyed by time spent on the hidden side, minimised with a sliding-window monotonic deque inside each interval. |
| 983C | 2400 | 2018 | Div1 | digit DP, bitmask DP over subsets, tree DP with rerooting | DP state tracks employees loaded so far, current floor, and the destination-floor multiset of the up-to-4 passengers still inside the elevator. |
| 1188C | 2500 | 2019 | Div1 | segment tree / BIT, standard DP over one dimension, shortest paths | Sort, then sum over thresholds x the count of k-subsequences whose gaps all exceed x, counted by prefix-sum DP with two pointers. |
| 1301E | 2500 | 2020 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | DP computes each cell's max valid quarter-colored square size, a 2D sparse table answers range-max, and binary search per query finds the best size. |
| 1497E2 | 2500 | 2021 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Sieve square-free parts, then DP over positions by changes used, two pointers giving the longest valid segment for each change budget. |
| 1556F | 2500 | 2021 | Div1+2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Winners form the top SCC; subset DP gives the probability each mask is strongly connected, times the probability it beats all outsiders. |
| 1661E | 2500 | 2022 | Div2 | two pointers, prefix sums, sorting + greedy | Components = cells - adjacencies + cycles via prefix sums; cycles are 2x2 free blocks and rings around blocked middle-row runs, clipped per query. |
| 1691F | 2500 | 2022 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Reroot the tree, tracking how many size-k subsets each edge separates from the root's rooted subtree, to sum f(r,S) in linear time per root. |
| 1778E | 2500 | 2023 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | XOR linear basis per subtree merged bottom-up, plus a rerooted outside-basis from prefix/suffix child merges for the complement case. |
| 1783F | 2500 | 2023 | Div2 | lazy propagation, SOS DP, matrix exponentiation, flows | Cycle-decompose both permutations; maximum bipartite matching between a-cycles and b-cycles picks skippable indices, so the answer is n minus the matching. <!-- unsure --> |
| 1796E | 2500 | 2023 | Div2 | digit DP, bitmask DP over subsets, tree DP with rerooting | Partition into vertical chains: each vertex extends its shortest child chain and finalizes the rest; reroot with multisets over all roots. |
| 2248F | 2500 | 2026 | Div2 | none | Decompose the decrement matrix's minimum-rectangle-operation cost via 2D differences, then optimize which cells to force into peaks within a budget. |
| 912C | 2500 | 2018 | Div2 | two pointers, prefix sums, sorting + greedy | Per enemy derive the time intervals where health <= damage, sweep sorted interval events counting kills, maximize count*(bounty+t*increase); detect the infinite case. |
| 976D | 2500 | 2018 | Div2 | none | Recurse: d_1 vertices joined to everything give degree d_n, d_n-d_{n-1} vertices joined only to them give d_1, middle recurses on degrees shifted by d_1. |
| 1218C | 2600 | 2019 | Div1 | segment tree / BIT, standard DP over one dimension, shortest paths | Match each transformer's period-4 cycle time to the path's fixed diagonal-time to place its cost on one grid cell, then DP the path. |
| 1391E | 2600 | 2020 | Div2 | DSU, basic graph traversal with a twist, binary search on answer | DFS tree ensures only ancestor-descendant edges; if depth is small, pair tree-siblings by parent, else the deep root-to-leaf chain itself is the long path. |
| 1439B | 2600 | 2020 | Div1 | DSU, basic graph traversal with a twist, binary search on answer | Peel the k-core with a queue; when a vertex reaches degree k-1 test its neighbourhood for a clique, cheap since k = O(sqrt(m)). |
| 1446D1 | 2600 | 2020 | Div1 | two pointers, prefix sums, sorting + greedy | The global mode is always a mode of the answer; for each other value find the longest zero-sum subarray using +1/-1 weights. |
| 1599J | 2600 | 2021 | Div1 | none | Model each B_i as a graph edge; build a triangle with even sum, else two equal-sum pairs as a 4-cycle, rest pendant. |
| 1895F | 2600 | 2023 | Div2 | lazy propagation, SOS DP, matrix exponentiation, flows | Count difference shapes: (x+k)(2k+1)^(n-1) minus a matrix-exponentiated count of shapes whose range stays below x, since max>=x forces the window. |
| 1905F | 2600 | 2023 | Div2 | none | Good indices are prefix-max breakpoints splitting p into consecutive value-blocks; find which single swap fixing/merging blocks maximizes new breakpoints. |
| 2003E1 | 2600 | 2024 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Each interval is a small-prefix then large-suffix; DP over positions by number of larges maximizes 10-pairs, plus C(c0,2)+C(c1,2) intra-group inversions. |
| 2231F | 2600 | 2026 | Div2 | none | Distances follow Legendre's sum-of-three-squares theorem (mod-8 exceptions add one), with small differences resolved by direct BFS over nearby vertices. |
| 935F | 2600 | 2018 | Div2 | segment tree / BIT, standard DP over one dimension, shortest paths | Keep the difference array (a range add is two point updates); a segment tree of max/min finds the element whose bump most raises the absolute-difference sum. |

**171 anchors**, drawn from the frozen corpus in the skill's build-time calibration data.
Ratings come from the Codeforces API and are labels, not estimates. Rows marked
`<!-- unsure -->` had a summary the summarizer could not reconcile with the true rating;
prefer another anchor when one is available.

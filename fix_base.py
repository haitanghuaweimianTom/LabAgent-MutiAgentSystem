import sys
path = r'E:\cherryClaw\math_modeling_multi_agent\backend\app\agents\base.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the end of the sensitivity code block - "code = ''''import numpy as np\nfrom scipy.optimize"
code_marker = "code = '''import numpy as np\nfrom scipy.optimize"
end_idx = content.find(code_marker)
print(f"Code marker found at: {end_idx}")

if end_idx < 0:
    print("Code marker not found!")
    # Try variations
    for variant in [
        "code = '''import numpy",
        "code = '''import numpy as np",
        "code = '''import",
    ]:
        idx = content.find(variant)
        print(f"  '{variant}' at: {idx}")
    sys.exit(1)

# Check what's before it
print(f"Before code marker: {repr(content[end_idx-100:end_idx+30])}")

topsis_code = """
                elif any(kw in block_lower for kw in ["评价", "topsis", "综合", "品类", "ahp"]):
                    code = '''import numpy as np

def topsis_evaluate(decision_matrix, weights, beneficial_indices):
    norm_matrix = decision_matrix / np.sqrt((decision_matrix ** 2).sum(axis=0))
    weighted = norm_matrix * weights
    ideal_pos = weighted.max(axis=0)
    ideal_neg = weighted.min(axis=0)
    for idx in beneficial_indices:
        ideal_pos[idx], ideal_neg[idx] = ideal_neg[idx], ideal_pos[idx]
    d_pos = np.sqrt(((weighted - ideal_pos) ** 2).sum(axis=1))
    d_neg = np.sqrt(((weighted - ideal_neg) ** 2).sum(axis=1))
    closeness = d_neg / (d_pos + d_neg)
    rankings = np.argsort(closeness)[::-1] + 1
    return {"rankings": rankings.tolist(), "closeness": closeness.tolist(), "best": rankings[0]}

if __name__ == "__main__":
    data = np.array([[50, 0.1, 0.95, 1000], [45, 0.08, 0.92, 950], [55, 0.12, 0.98, 1200], [48, 0.09, 0.94, 980], [52, 0.11, 0.96, 1100]])
    weights = np.array([0.3, 0.2, 0.3, 0.2])
    result = topsis_evaluate(data, weights, beneficial_indices=[0, 2, 3])
    print("品类排名:", result["rankings"])
    print("贴近度:", [round(c, 3) for c in result["closeness"]])'''
"""

new_content = content[:end_idx] + topsis_code + content[end_idx:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
print(f"Done! File now {len(new_content)} chars (was {len(content)})")
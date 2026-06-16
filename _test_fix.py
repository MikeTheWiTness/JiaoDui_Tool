import json

VALID = set(['"', '\', '/', 'b', 'f', 'n', 'r', 't'])

def fix(s):
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == 'u':
                result.append('\')
            elif nxt in VALID:
                if i + 2 < len(s) and s[i + 2].isalpha():
                    result.append('\\')
                else:
                    result.append('\')
            else:
                result.append('\\')
            i += 1
        else:
            result.append(s[i])
        i += 1
    return ''.join(result)

with open("output/校对报告/第 1 讲校对测试1_校对报告.md", encoding="utf-8") as f:
    content = f.read()

start = content.find("## 第3题")
end = content.find("---", start)
section = content[start:end]
brace_s = section.find("{")
brace_e = section.rfind("}")
txt = section[brace_s:brace_e+1]

try:
    json.loads(txt)
    print("bare parse OK")
except:
    fixed = fix(txt)
    try:
        json.loads(fixed)
        print("fixed parse OK")
    except json.JSONDecodeError as e:
        print("STILL FAILED:", e)

import json, sys, glob, os, re, collections
res = sys.argv[1]
cnt = collections.Counter(); per = collections.defaultdict(set); empty=[]
for f in sorted(glob.glob(res + '/*.json')):
    name = os.path.basename(f)[:-5]
    txt = open(f).read().strip().replace('&gt;','>').replace('&lt;','<').replace('&amp;','&').replace('&quot;','"')
    if not txt: empty.append(name); continue
    d = json.loads(txt)
    for x in d['fails']:
        k = x.split(' ')[0]
        cnt[k] += 1
        per[re.sub(r'\d+(\.\d+)?px|\[[^\]]*\]|\d+>\d+|\d+x\d+', '#', x)[:150]].add(name.rsplit('-',1)[1])
print('pages with no result:', len(empty), empty[:5])
print(dict(cnt))
for k, v in sorted(per.items(), key=lambda kv: kv[0]):
    print(sorted(v, key=int), k)

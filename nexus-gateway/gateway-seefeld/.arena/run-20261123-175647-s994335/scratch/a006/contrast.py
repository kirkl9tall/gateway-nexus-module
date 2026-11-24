def L(h):
    h=h.lstrip('#'); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    x,y=sorted([L(a),L(b)],reverse=True); return (x+0.05)/(y+0.05)
pairs={
 'light': [('#17202A','#FFFFFF'),('#4B5763','#F3F6F7'),('#5F6B77','#FFFFFF'),('#5F6B77','#F3F6F7'),('#2C5F8A','#E6EEF5'),('#234C6F','#E6EEF5'),
   ('#1E7A46','#E3F2E9'),('#8A5A00','#FBF1DA'),('#B42318','#FBE6E3'),('#5F6B77','#ECEFF2'),('#FFFFFF','#1E7A46'),('#FFFFFF','#B42318'),('#FFFFFF','#2C5F8A'),('#17202A','#E9A820'),
   ('#2C5F8A','#FFFFFF'),('#5F6B77','#E6EEF5'),('#7D9AB5','#FFFFFF'),('#1E7A46','#FFFFFF'),('#B42318','#FFFFFF')],
 'dark': [('#E6EAED','#1C2023'),('#E6EAED','#141719'),('#C3CAD1','#1C2023'),('#A3ADB7','#1C2023'),('#A3ADB7','#141719'),('#8DB6DD','#1C2023'),('#8DB6DD','#22303D'),('#A9C9E8','#22303D'),
   ('#5CC48A','#1C2023'),('#5CC48A','#173324'),('#F0B849','#1C2023'),('#F0B849','#3A2E12'),('#F08A7E','#1C2023'),('#F08A7E','#3D1F1B'),('#A3ADB7','#2A3036'),
   ('#10161B','#5CC48A'),('#10161B','#F08A7E'),('#10161B','#8DB6DD'),('#10161B','#F0B849'),('#5CC48A','#141719'),('#F08A7E','#141719'),('#4F7392','#1C2023'),('#E6EAED','#3A4148')],
}
for k,v in pairs.items():
    print(k)
    for a,b in v: print(f'  {a} on {b}: {cr(a,b):.2f}')

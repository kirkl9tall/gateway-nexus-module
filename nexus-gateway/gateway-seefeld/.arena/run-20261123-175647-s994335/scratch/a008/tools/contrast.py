def lum(h):
    h=h.lstrip('#'); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    la,lb=sorted([lum(a),lum(b)],reverse=True); return (la+0.05)/(lb+0.05)
L=dict(page='#F3F6F7',surface='#FFFFFF',ink='#17202A',ink2='#4B5763',ink3='#5F6B77',line='#D5DCE1',brand='#2C5F8A',brandtint='#E6EEF5',good='#1E7A46',goodt='#E3F2E9',warn='#8A5A00',warnt='#FBF1DA',warnfill='#E9A820',crit='#B42318',critt='#FBE6E3',neu='#5F6B77',neut='#ECEFF2',onbrand='#FFFFFF',brand2='#234C6F')
D=dict(page='#141719',surface='#1C2023',ink='#E6EAEE',ink2='#C3CBD3',ink3='#A2ADB8',line='#3A424A',brand='#8CB8E0',brandtint='#1F3347',good='#6CCF96',goodt='#173323',warn='#F0C060',warnt='#3A2E12',warnfill='#E9A820',crit='#FF9C90',critt='#41201C',neu='#A2ADB8',neut='#2A3138',onbrand='#0F1A24',brand2='#A9CCEC')
for name,P in (('LIGHT',L),('DARK',D)):
    print(name)
    pairs=[('ink','surface'),('ink','page'),('ink2','surface'),('ink2','page'),('ink3','surface'),('ink3','page'),('brand','surface'),('brand','page'),('brand2','brandtint'),('onbrand','brand'),('onbrand','brand2'),
           ('good','goodt'),('warn','warnt'),('crit','critt'),('neu','neut'),('good','surface'),('crit','surface'),('warn','surface'),('ink','brandtint'),('ink','warnfill'),('line','surface'),('warnfill','surface'),('good','page'),('neu','surface')]
    for a,b in pairs: print(f'  {a:8} on {b:9} {cr(P[a],P[b]):.2f}')
    print('  white on good', round(cr('#FFFFFF',P['good']),2), ' onstatus dark on good', round(cr('#0F1A24',P['good']),2), round(cr('#0F1A24',P['crit']),2), round(cr('#FFFFFF',P['crit']),2))

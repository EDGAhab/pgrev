"""rev4-exp2 diagnostic figure: regenerated vs naive-copy around the macro."""
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

def load_old():
    rows = list(csv.DictReader(open('/home/hatch/pgrev/data/sky130hd_gcd_unlabeled/pg_shapes.csv')))
    out = []
    for r in rows:
        if r['kind'] != 'wire' or r['layer'] not in ('met4', 'met5'):
            continue
        out.append((r['net'], r['layer'], *(int(r[k]) for k in ('x1','y1','x2','y2'))))
    return out

def load_new():
    rows = list(csv.DictReader(open('/tmp/rev4/exp2/pg_shapes_new.csv')))
    out = []
    for r in rows:
        if r['via_name'] or r['layer'] not in ('met4', 'met5'):
            continue
        out.append((r['net'], r['layer'], *(int(r[k]) for k in ('x1','y1','x2','y2'))))
    return out

# zoom window um
X0, X1, Y0, Y1 = 95, 215, 95, 215
MX1, MY1, MX2, MY2 = 130, 130, 180, 180      # macro
HX1, HY1, HX2, HY2 = 128, 128.24, 182, 181.76  # halo boundary used by pdngen

def draw(ax, wires, title):
    for net, layer, x1, y1, x2, y2 in wires:
        if x2 < X0*1000 or x1 > X1*1000 or y2 < Y0*1000 or y1 > Y1*1000:
            continue
        color = {'met4': '#1f77b4', 'met5': '#ff7f0e'}[layer]
        ls = '-' if net == 'VDD' else '--'
        ax.add_patch(Rectangle((x1/1000, y1/1000), (x2-x1)/1000, (y2-y1)/1000,
                               facecolor=color, edgecolor='none', alpha=0.55))
    ax.add_patch(Rectangle((MX1, MY1), MX2-MX1, MY2-MY1, facecolor='none',
                           edgecolor='red', linewidth=2))
    ax.add_patch(Rectangle((HX1, HY1), HX2-HX1, HY2-HY1, facecolor='none',
                           edgecolor='red', linewidth=1, linestyle=':'))
    ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect('equal')
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('um'); ax.set_ylabel('um')

fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6.2))
draw(a1, load_new(), 'Regenerated: recovered spec on new floorplan\nstripes stop at halo boundary')
draw(a2, load_old(), 'Control: naive copy of original polygons\n8 stripes pierce the macro, 122 vias land inside')
for ax in (a1, a2):
    ax.plot([], [], color='#1f77b4', linewidth=6, label='met4 stripe (V)')
    ax.plot([], [], color='#ff7f0e', linewidth=6, label='met5 stripe (H)')
    ax.plot([], [], color='red', linewidth=2, label='macro 130-180um')
    ax.legend(fontsize=8, loc='upper left')
fig.suptitle('rev4-exp2: end-to-end attack demo (sky130hd/gcd + inserted 50x50um macro)', fontsize=12)
fig.tight_layout()
fig.savefig('/home/hatch/pgrev/reports/rev4-exp2-e2e.png', dpi=110)
print('wrote reports/rev4-exp2-e2e.png')

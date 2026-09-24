#!/usr/bin/env python3
"""
gen_schematic.py — генерация uPC1237_SSR.asc (формат LTspice IV, "Version 4") из uPC1237_SSR.cir.

Принцип: топология берётся ТОЛЬКО из .cir (единый источник истины). Каждый элемент рисуется
стандартным символом LTspice, каждый вывод подписывается FLAG-меткой (имя цепи). Провода-«щупы»
длиннее реальных выводов символа, поэтому попадают в вывод при любом разумном шаге вывода
(см. таблицу допусков TOL ниже) — это делает .asc устойчивым к неточности геометрии символов.

TOL (допуски, использованные для «щупов»):
  2-выводные (res/cap/diode/voltage) в ориентации R90: вывод1 в (x,y), вывод2 в (x+span,y), span=64..96
      щуп1: (x-40,y)-(x+16,y) ; щуп2: (x+56,y)-(x+136,y)
  nmos: затвор (-64,0), сток (0,-96), исток (0,+48), подложка (0,+16)
      щуп затвора: (x-80,y)-(x-16,y) ; щупы стока/истока покрывают (0,-112..-24) и (0,-8..+80) =>
      подложка тоже садится на исток (как в .cir: M с тремя узлами).
  4-выводный ключ sw: основные выводы (±64,0), управляющие (±32,-64)
      щуп A: (x-96,y)-(x-24,y) ; щуп B: (x+24,y)-(x+96,y) ; управление: (x-48,y-80)-(x+48,y-48)
"""
import os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, 'uPC1237_SSR.cir')
OUT  = os.path.join(ROOT, 'uPC1237_SSR.asc')
GRID = 16

def parse(path):
    lines, els, dirs = [], [], []
    for raw in open(path, encoding='utf-8'):
        ln = raw.strip()
        if not ln or ln.startswith('*'):
            continue
        t = ln.split(';')[0].split()
        if not t:
            continue
        name = t[0]
        if name.startswith('.'):
            dirs.append(ln.split(';')[0].strip())
        else:
            els.append(t)
    return els, dirs

def sym_of(name, toks):
    p = name[0].upper()
    if p == 'M': return 'nmos', 3
    if p == 'R': return 'res', 2
    if p == 'C': return 'cap', 2
    if p == 'D': return 'diode', 2
    if p == 'V': return 'voltage', 2
    if p == 'I': return 'current', 2
    if p == 'S': return 'sw', 4
    if p == 'B': return ('bv' if len(toks) > 3 and toks[3] == 'V' else 'bi'), 2
    return None, 0

def main():
    els, dirs = parse(SRC)
    out = ['Version 4', 'SHEET 1 2800 1600']
    x0, y0, dx, dy = 160, 200, 340, 170
    placed, nodes = [], set()
    for i, t in enumerate(els):
        sym, npin = sym_of(t[0], t)
        if sym is None:
            print('SKIP (нет символа):', t[0], file=sys.stderr); continue
        col, row = i % 7, i // 7
        x, y = x0 + col * dx, y0 + row * dy
        val = ' '.join(t[1 + npin:]) if len(t) > 1 + npin else ''
        if sym in ('res', 'cap', 'diode', 'voltage', 'current', 'bi', 'bv'):
            conns = t[1:3]
            out.append(f'SYMBOL {sym} {x} {y} R90')
            out.append(f'SYMATTR InstName {t[0].upper()}')
            out.append(f'SYMATTR Value {val if val else "0"}')
            stubs = [(x - 40, y, x + 16, y, conns[0]), (x + 56, y, x + 136, y, conns[1])]
        elif sym == 'nmos':
            conns = t[1:4]
            out.append(f'SYMBOL nmos {x} {y} R0')
            out.append(f'SYMATTR InstName {t[0].upper()}')
            out.append(f'SYMATTR Value {val}')
            stubs = [(x - 80, y, x - 16, y, conns[1]),          # затвор
                     (x, y - 112, x, y - 24, conns[0]),          # сток
                     (x, y - 8, x, y + 80, conns[2])]            # исток (+подложка)
        elif sym == 'sw':
            conns = t[1:5]
            out.append(f'SYMBOL sw {x} {y} R0')
            out.append(f'SYMATTR InstName {t[0].upper()}')
            out.append(f'SYMATTR Value {val}')
            stubs = [(x - 96, y, x - 24, y, conns[0]), (x + 24, y, x + 96, y, conns[1]),
                     (x - 48, y - 80, x + 48, y - 48, conns[2] + ' / ' + conns[3])]
        for (a, b, c, d, net) in stubs:
            out.append(f'WIRE {a} {b} {c} {d}')
        for (a, b, c, d, net) in stubs:
            for nn in re.split(r'\s*/\s*', net.strip()):
                if nn:
                    nodes.add(nn)
                    out.append(f'FLAG {a + 4 if c > a else a} {b} {nn}')
                    break
        placed.append((sym, x, y))
    for i, d in enumerate(dirs):
        col, row = divmod(i, 18)
        out.append(f'TEXT {2200 + col * 300} {200 + row * 40} Left 2 !{d}')
    open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    # --- структурная проверка ---
    txt = open(OUT, encoding='utf-8').read()
    insts = re.findall(r'SYMATTR InstName (\S+)', txt)
    vals  = re.findall(r'SYMATTR Value (.+)', txt)
    src_nodes = set()
    for t in els:
        sym, npin = sym_of(t[0], t)
        if sym == 'nmos':
            nn_list = t[1:4]
        elif sym == 'sw':
            nn_list = t[1:5]
        else:
            nn_list = t[1:3]
        for nn in nn_list:
            src_nodes.add(nn)
    print(f'elements={len(els)} symbols={len(insts)} values={len(vals)} '
          f'unique_inst={len(set(insts))}')
    print('узлы с FLAG:', len(nodes))
    print('узлы .cir без FLAG:', sorted(n for n in src_nodes - nodes if not n.isdigit()))
    print('FLAG вне .cir:', sorted(nodes - src_nodes))
    assert len(insts) == len(set(insts)), 'дубли InstName'
    assert len(vals) == len(insts), 'не у всех символов есть Value'
    print('OK ->', OUT)

if __name__ == '__main__':
    main()

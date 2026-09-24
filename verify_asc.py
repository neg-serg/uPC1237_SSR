#!/usr/bin/env python3
"""verify_asc.py — проверка, что uPC1237_SSR.asc и uPC1237_SSR.cir описывают одну и ту же схему.

Что делает: читает .asc (как это делает LTspice), строит из геометрии нетлист
(провода соединяют точки с одинаковыми координатами, FLAG-метка даёт имя узла),
и сверяет его с .cir поэлементно: имена узлов по порядку выводов (SpiceOrder) и значение.

Проверки:
  1. каждый вывод каждого символа лежит на проводе (щупе), узел имеет имя (FLAG);
  2. порядок узлов в .asc = порядок узлов в .cir (иначе LTspice соединит не то);
  3. значения (модель/номинал) совпадают;
  4. все директивы .cir (.param/.model/.options/.tran/.meas) присутствуют в .asc текстом.
Код возврата 0 — эквивалентно, 1 — расхождения.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_schematic import PINS, ORIENT, pins_world, parse, sym_of   # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
ASC = os.path.join(ROOT, 'uPC1237_SSR.asc')
CIR = os.path.join(ROOT, 'uPC1237_SSR.cir')


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def read_asc(path):
    syms, wires, flags, texts = [], [], {}, []
    cur = None
    for raw in open(path, encoding='utf-8'):
        ln = raw.strip()
        if ln.startswith('SYMBOL'):
            _, name, x, y, *o = ln.split()
            cur = {'sym': name, 'x': int(x), 'y': int(y), 'orient': o[0] if o else 'R0'}
            syms.append(cur)
        elif ln.startswith('SYMATTR InstName'):
            cur['inst'] = ln.split(None, 2)[2]
        elif ln.startswith('SYMATTR Value'):
            cur['value'] = ln.split(None, 2)[2]
        elif ln.startswith('WIRE'):
            _, x1, y1, x2, y2 = ln.split()
            wires.append(((int(x1), int(y1)), (int(x2), int(y2))))
        elif ln.startswith('FLAG'):
            _, x, y, name = ln.split(None, 3)
            flags[(int(x), int(y))] = name
        elif ln.startswith('TEXT'):
            texts.append(ln.split('!', 1)[1] if '!' in ln else '')
    return syms, wires, flags, texts


def asc_netlist(syms, wires, flags):
    """Нетлист из геометрии: провода соединяют точки с одинаковыми координатами, FLAG даёт имя узла."""
    dsu = DSU()
    endpoints = set()
    for a, b in wires:
        dsu.union(a, b)
        endpoints |= {a, b}
    named = {}
    problems = []
    for coord, name in flags.items():
        root = dsu.find(coord)
        if root in named and named[root] != name:
            problems.append(f'одному узлу {coord} дали два имени: {named[root]} и {name}')
        named[root] = name
    out = {}
    for s in syms:
        nodes = []
        for (name, wx, wy, dx, dy) in pins_world(s['sym'], s['x'], s['y'], s['orient']):
            pin, end = (wx, wy), (wx + dx * 32, wy + dy * 32)
            if pin not in endpoints:
                problems.append(f"{s['inst']}.{name}: вывод ({wx},{wy}) не соединён проводом")
            elif end not in endpoints:
                problems.append(f"{s['inst']}.{name}: щуп обрывается в пустоту ({end})")
            node = named.get(dsu.find(pin)) or named.get(dsu.find(end))
            if node is None:
                problems.append(f"{s['inst']}.{name}: у узла нет FLAG-метки")
            nodes.append(node)
        out[s['inst']] = (nodes, s.get('value', ''))
    return out, problems


def cir_netlist(path):
    els, dirs = parse(path)
    out = {}
    for t in els:
        sym, npin = sym_of(t[0], t)
        out[t[0]] = (list(t[1:1 + npin]), ' '.join(t[1 + npin:]))
    return out, dirs


def main():
    syms, wires, flags, texts = read_asc(ASC)
    asc, problems = asc_netlist(syms, wires, flags)
    cir, dirs = cir_netlist(CIR)
    ok = True

    if problems:
        ok = False
        print('ПРОБЛЕМЫ ГЕОМЕТРИИ:')
        for p in problems:
            print('  -', p)

    for name, (nodes, value) in cir.items():
        if name not in asc:
            print(f'НЕТ В .asc: {name}')
            ok = False
            continue
        got_nodes, got_value = asc[name]
        if [n.upper() for n in got_nodes] != [n.upper() for n in nodes]:
            print(f'УЗЛЫ НЕ СОВПАЛИ {name}: .asc={got_nodes} .cir={nodes}')
            ok = False
        if got_value.strip() != value.strip():
            print(f'ЗНАЧЕНИЕ НЕ СОВПАЛО {name}: .asc={got_value!r} .cir={value!r}')
            ok = False

    extra = set(asc) - set(cir)
    if extra:
        print('ЛИШНИЕ В .asc:', sorted(extra))
        ok = False

    text = '\n'.join(texts)
    for d in dirs:
        if ' '.join(d) not in text:
            print('НЕТ ДИРЕКТИВЫ В .asc TEXT:', ' '.join(d))
            ok = False

    print(f'элементов: .cir={len(cir)}  .asc={len(asc)}   проводов: {len(wires)}   '
          f'меток: {len(flags)}   директив: {len(dirs)}')
    print('ИТОГ:', 'OK — .asc эквивалентен .cir (по узлам, значениям и директивам)' if ok
          else 'РАСХОЖДЕНИЯ НАЙДЕНЫ')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

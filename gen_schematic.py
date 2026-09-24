#!/usr/bin/env python3
"""gen_schematic.py — генерация uPC1237_SSR.asc (формат LTspice IV, "Version 4") из uPC1237_SSR.cir.

Топология берётся ТОЛЬКО из .cir (единый источник истины). Каждый элемент рисуется
стандартным символом LTspice; каждый вывод символа соединяется проводом-«щупом» (stub, 32 px),
на конце щупа ставится FLAG-метка с именем цепи. Связи между элементами — по именам цепей
(в LTspice одни и те же имена цепей = один узел), поэтому маршрутизация проводов не нужна.

ГЕОМЕТРИЯ. Координаты выводов берутся из таблицы «Standard Symbol Pin Offsets» официальной
документации LTspice (analogdevicesinc/ltspice-reference, ai_ref/SCHEMATIC-REFERENCE.md) —
это локальные смещения из .asy, порядок = SpiceOrder (порядок узлов в строке нетлиста).

Ориентации (см. тот же документ, «Pin World-Coordinate Calculation»):
    R0 : (sx + px, sy + py)
    R90: (sx - py, sy + px)

ВАЖНО: провод соединяется с выводом ТОЛЬКО при точном совпадении координат, поэтому щупы
начинаются ровно в координате вывода. Позиции символов лежат на сетке 16.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'uPC1237_SSR.cir')
OUT = os.path.join(ROOT, 'uPC1237_SSR.asc')
GRID = 16
STUB = 32  # длина щупа, px

# имя символа -> [(имя вывода, px, py)] в порядке SpiceOrder
PINS = {
    'res':     [('A', 16, 16), ('B', 16, 96)],
    'cap':     [('A', 16, 0),  ('B', 16, 64)],
    'diode':   [('+', 16, 0),  ('-', 16, 64)],
    'voltage': [('+', 0, 16),  ('-', 0, 96)],
    'current': [('+', 0, 0),   ('-', 0, 80)],
    'bi':      [('+', 0, 0),   ('-', 0, 80)],
    'bv':      [('+', 0, 16),  ('-', 0, 96)],
    'nmos':    [('D', 48, 0),  ('G', 0, 80),  ('S', 48, 96)],
    'sw':      [('A', 0, 16),  ('B', 0, 96),  ('NC+', -48, 80), ('NC-', -48, 32)],
}

# направление щупа в мировых координатах: (символ, ориентация) -> [dir по индексу вывода]
STUB_DIR = {
    ('res', 'R90'):     [(1, 0), (-1, 0)],
    ('cap', 'R90'):     [(1, 0), (-1, 0)],
    ('diode', 'R90'):   [(1, 0), (-1, 0)],
    ('voltage', 'R90'): [(1, 0), (-1, 0)],
    ('current', 'R90'): [(1, 0), (-1, 0)],
    ('bi', 'R90'):      [(1, 0), (-1, 0)],
    ('bv', 'R90'):      [(1, 0), (-1, 0)],
    ('nmos', 'R0'):     [(0, -1), (-1, 0), (0, 1)],
    ('sw', 'R0'):       [(1, 0), (1, 0), (-1, 0), (-1, 0)],
}

ORIENT = {'res': 'R90', 'cap': 'R90', 'diode': 'R90', 'voltage': 'R90', 'current': 'R90',
          'bi': 'R90', 'bv': 'R90', 'nmos': 'R0', 'sw': 'R0'}


def rotate(px, py, sx, sy, orient):
    if orient == 'R0':
        return sx + px, sy + py
    if orient == 'R90':
        return sx - py, sy + px
    raise ValueError(orient)


def pins_world(sym, sx, sy, orient):
    """[(имя вывода, wx, wy, dirx, diry)] — мировые координаты выводов и направление щупа."""
    dirs = STUB_DIR[(sym, orient)]
    return [(name, *rotate(px, py, sx, sy, orient), *dirs[i])
            for i, (name, px, py) in enumerate(PINS[sym])]


def parse(path):
    els, dirs = [], []
    for raw in open(path, encoding='utf-8'):
        ln = raw.strip()
        if not ln or ln.startswith('*'):
            continue
        t = ln.split(';')[0].split()
        if not t:
            continue
        (dirs if t[0].startswith('.') else els).append(t)
    return els, dirs


def sym_of(name, toks):
    """(символ LTspice, число выводов) для элемента .cir; None — рисовать нечем."""
    p = name[0].upper()
    if p == 'M':
        return 'nmos', 3
    if p == 'R':
        return 'res', 2
    if p == 'C':
        return 'cap', 2
    if p == 'D':
        return 'diode', 2
    if p == 'V':
        return 'voltage', 2
    if p == 'I':
        return 'current', 2
    if p == 'S':
        return 'sw', 4
    if p == 'B':
        return ('bv' if len(toks) > 3 and toks[3].upper() == 'V' else 'bi'), 2
    return None, 0


def main():
    els, dirs = parse(SRC)
    lines = ['Version 4', 'SHEET 1 2800 1600']
    x0, y0, dx, dy, cols = 192, 192, 320, 192, 7
    nodes, stub_ends, pin_coords, skipped = set(), set(), set(), []
    n_sym = 0

    for i, t in enumerate(els):
        sym, npin = sym_of(t[0], t)
        if sym is None:
            skipped.append(t[0])
            continue
        col, row = i % cols, i // cols
        x, y = x0 + col * dx, y0 + row * dy
        orient = ORIENT[sym]
        val = ' '.join(t[1 + npin:]) if len(t) > 1 + npin else ''

        lines += [f'SYMBOL {sym} {x} {y} {orient}',
                  f'SYMATTR InstName {t[0]}',
                  f'SYMATTR Value {val if val else "0"}']
        n_sym += 1

        for (name, wx, wy, dirx, diry) in pins_world(sym, x, y, orient):
            ex, ey = wx + dirx * STUB, wy + diry * STUB
            lines.append(f'WIRE {wx} {wy} {ex} {ey}')

        for k, (name, wx, wy, dirx, diry) in enumerate(pins_world(sym, x, y, orient)):
            net = t[1 + k]
            nodes.add(net)
            ex, ey = wx + dirx * STUB, wy + diry * STUB
            lines.append(f'FLAG {ex} {ey} {net}')
            assert (ex, ey) not in stub_ends, f'щупы совпали: {t[0]}/{name}'
            stub_ends.add((ex, ey))
            assert (wx, wy) not in pin_coords, f'два вывода в одной точке: {t[0]}/{name}'
            pin_coords.add((wx, wy))

    for i, d in enumerate(dirs):
        col, row = divmod(i, 26)
        lines.append(f'TEXT {2400 + col * 480} {192 + row * 40} Left 2 !{" ".join(d)}')

    open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    # --- структурные проверки геометрии и состава ---
    bad_grid = [c for c in (set(stub_ends) | pin_coords) if c[0] % GRID or c[1] % GRID]
    crossings = set(stub_ends) & pin_coords                       # щуп сел на чужой вывод
    src_nodes = {n for t in els for n in (t[1:4] if t[0][0].upper() == 'M' else
                                          t[1:5] if t[0][0].upper() == 'S' else t[1:3])}
    txt = open(OUT, encoding='utf-8').read()
    insts = re.findall(r'SYMATTR InstName (\S+)', txt)
    vals = re.findall(r'SYMATTR Value (.+)', txt)
    print(f'элементов в .cir: {len(els)}   символов в .asc: {n_sym}   '
          f'InstName: {len(insts)}   Value: {len(vals)}')
    print(f'выводов размещено: {len(pin_coords)}   щупов: {len(stub_ends)}   '
          f'узлов с FLAG: {len(nodes)}')
    print('вне сетки 16:', bad_grid or 'нет')
    print('щуп попал в чужой вывод:', sorted(crossings) or 'нет')
    print('узлы .cir без FLAG:', sorted(n for n in src_nodes - nodes if not n.isdigit()) or 'нет')
    print('FLAG вне .cir:', sorted(nodes - src_nodes) or 'нет')
    print('пропущено (нет символа):', skipped or 'нет')
    print('директив .cir перенесено в TEXT:', len(dirs))
    assert not bad_grid and not crossings, 'геометрия схемы некорректна'
    assert sorted(insts) == sorted(t[0] for t in els), 'не все элементы нарисованы'
    assert len(vals) == len(insts), 'не у всех символов есть Value'
    print('OK ->', OUT)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""gen_bom.py — BOM собирается ИЗ uPC1237_SSR.cir: значения не могут разойтись с мастером.
Значение каждой позиции берётся из строки элемента, из .param или из .model (см. 10-ю колонку)."""
import re, csv, os
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC, DST = os.path.join(ROOT, 'uPC1237_SSR.cir'), os.path.join(ROOT, 'BOM.csv')
TXT = open(SRC, encoding='utf-8').read()
EL = {}
for ln in TXT.splitlines():
    t = ln.split(';')[0].split()
    if t and not t[0].startswith(('.', '*')): EL[t[0].upper()] = t

def val(spec):
    kind = spec[0]
    if kind == 'const': return spec[1]
    if kind == 'el':
        t = EL.get(spec[1].upper()); assert t, f'{spec[1]} нет в мастере'
        assert len(t) > 3, f'{spec[1]}: нет значения'
        v = t[3]
        if v.startswith('{') and v.endswith('}'):          # {PARAM} -> подставить .param
            m = re.search(rf'\b{v[1:-1]}=(\S+)', TXT); assert m, f'param {v[1:-1]} не найден'
            v = m.group(1)
        return v
    if kind == 'param':
        m = re.search(rf'\b{spec[1]}=(\S+)', TXT); assert m, f'param {spec[1]} не найден'
        return m.group(1)
    m = re.search(rf'\.model\s+{spec[1]}\s+\w+\(([^)]*)\)', TXT, re.I); assert m, f'model {spec[1]} не найден'
    mm = re.search(rf'{spec[2]}=([0-9.eE+-]+)', m.group(1), re.I); assert mm, f'{spec[1]}:{spec[2]} нет'
    return f'{spec[2]}={mm.group(1)}'

# refdes, qty, rating, tol, power, package, mfr, partnumber, notes, источник значения
HW = [
 ('U1',1,'Vcc 25..60 В','-','Pd 320 мВт (Ta=75 C)','DIP-8 / SIP-8','NEC / Renesas','UPC1237HA','макромодель проверена в ngspice; пороги из doc IC-1806A',('const','uPC1237')),
 ('U2',1,'IF<=50 мА, 3750 VRMS','-','-','SOP-4','Vishay','VOM1271T','VOC 7.8/8.4 В, ISC 15 мкА, встроенный разряд 140 кОм',('const','VOM1271T')),
 ('Q1,Q2',2,'60 В / 20 А, Rds(on)<=1.9 мОм @Vgs=7 В','-','Pd 167 Вт','PG-TDSON-8','Infineon','IAUC120N06S5N015','MAIN; измерено 2.8 мОм/прибор (27 C), 3.1 мОм (100 C)',('const','60 В N-MOSFET')),
 ('M_BKP',2,'60 В, Rds(on)<=2.6 мОм @Vgs=4.5 В','-','Pd 375 Вт','TO-263','Vishay','SUM50020EL','резерв; Ciss 11.1 нФ => при пассивном разряде t_off 3.5 мс',('const','60 В N-MOSFET (резерв)')),
 ('R8',1,'Vcc dropper','5%','0.5 Вт','0805/MELF','-','-','от VCC45 к выводу 8 uPC1237',('el','R8')),
 ('D8',1,'стабилитрон V8','2%','0.5 Вт','SOD-123','-','BZX84C3V6','опорное 3.4 В (вывод 8); модель DZ8',('model','DZ8','BV')),
 ('R4',1,'сетевой AC-вход','1%','0.25 Вт','1206','-','-','AC-OFF (вывод 4); при питании от сети >=300 В изоляция',('el','R4')),
 ('C4',1,'AC-детекция','20%','-','X7R 50 В','-','-','с RINT4 (внутр. IC) => отключение 71 мс (TC6)',('el','C4')),
 ('R7',1,'T_ON','1%','0.25 Вт','0805','-','-','T_ON=0.931*R7*C7; измерено 4.36 с (TC1)',('el','R7')),
 ('C7',1,'T_ON','20%','-','электролит 16 В','-','-','задержка включения (ic=0 в модели)',('el','C7')),
 ('RA1,RB1',2,'DC-детекция','1%','0.25 Вт','0805','-','-','делитель вывода 2, порог ~2 В на выходе УМ',('el','RA1')),
 ('RC1',1,'DC-детекция','1%','0.25 Вт','0805','-','-','формулы (1)-(3) даташита, SPEC R7',('el','RC1')),
 ('C2',1,'DC-фильтр','20%','-','плёнка 16 В','-','-','T_DC: 176 мс (+3 В) / 33 мс (-3 В), TC3/TC4',('param','CS_DC')),
 ('C3',1,'latch','10%','-','X7R 50 В','-','-','вывод 3; latch-режим (R8)',('el','C3')),
 ('RLEAK',1,'режим latch','5%','0.25 Вт','0805','-','-','1 ГОм = latch; 10 кОм = auto-reset (TC7b)',('el','RLEAK')),
 ('RLED',1,'IF=10..15 мА','1%','0.25 Вт','0805','-','-','ветвь VHLOG -> RLED -> LED(U2) -> LED(OPT1) -> PIN6; IF=9.8 мА (TC1)',('param','RLIM')),
 ('RG1,RG2',2,'затвор','5%','0.125 Вт','0603','-','-','последовательно в затвор каждого MOSFET',('el','RG1')),
 ('RGS1,RGS2',2,'стягивание затвор-исток','5%','0.125 Вт','0603','-','-','Vgs=8.36 В (TC1); 1 МОм просаживал Vgs до 7.3 В',('el','RGS1')),
 ('CGS1,CGS2',2,'затвор-исток','10%','-','X7R 25 В / 0603','-','-','подавление drain-induced turn-on (наводка через Cgd при фронте стока 50 В); цена — включение ~26 мс',('el','CGS1')),
 ('DTVS1,DTVS2',2,'ограничитель выброса (OPT2)','5%','1 Вт','DO-41 / SMB','-','1.5KE51A (TVS) — 1 шт. ДВУНАПРАВЛЕННЫЙ, либо 2 стабилитрона 51 В ОБЩИМ АНОДОМ','ОБЯЗАТЕЛЕН: АС индуктивна; без него на размыкании 3784 В (TC13a), с ним 54.7 В < 60 В (TC13a/TC17). Правила: Vclamp < 0.9*Vds(ключ); Vclamp > рельсы + 15%; ЭНЕРГИЯ >= 0.5 Дж (1 Вт стабилитрон НЕ годится); включение — встречно С ОБЩИМ АНОДОМ (иначе шунтирует ключ, TC18)',('el','DTVS1')),
 ('OPT1',1,'активный разряд затвора (R11)','-','-','SOT-23 + SOP-4','-','BSS84 + EL357 + 4.7 Ом','в модели SDIS1/SDIS2 (Ron=5 Ом), управление током LED через развязку; t_off 0.8..1.8 мкс',('const','активный разряд затвора')),
 ('CPIN6',1,'фильтр вывода 6','10%','-','0603','-','-','ёмкость проводников/LED (в модели 100 пФ)',('el','CPIN6')),
]
rows = [[r, q, val(s), rat, tol, pw, pkg, mfr, pn, note] for r,q,rat,tol,pw,pkg,mfr,pn,note,s in HW]
with open(DST,'w',newline='',encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['RefDes','Qty','Value(from .cir/.param/.model)','Rating','Tolerance','Power','Package','Manufacturer','PartNumber','Notes'])
    w.writerows(rows)
tbd = sum(1 for r in rows if any('TBD' in str(x) for x in r))
print(f'BOM: {len(rows)} позиций, TBD={tbd}')
for r in rows: print(f'  {r[0]:10s} qty={r[1]} {r[2]:12s} {r[8] or "-"}')

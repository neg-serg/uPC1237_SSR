#!/usr/bin/env python3
"""Генератор tests/TC*.cir из мастер-нетлиста uPC1237_SSR.cir (маркеры SCENARIO/MEAS)."""
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
M = open(os.path.join(ROOT, 'uPC1237_SSR.cir'), encoding='utf-8').read()
HEAD = M.split('*<<<SCENARIO')[0]
MID  = M.split('*>>>SCENARIO')[1].split('*<<<MEAS')[0]
LOAD_BASE = "VSNS SPK SPKX 0\nRLOAD SPKX 0 8\n"
def build(scenario, meas, tran, temp=27, amp=None, extra_elems='', repl=None):
    txt = HEAD + extra_elems + '*<<<SCENARIO\n' + scenario + '*>>>SCENARIO' + MID
    txt += '.options reltol=1e-4 abstol=1e-10 vntol=1e-7 itl4=200\n'
    txt += f'.temp {temp}\n' + tran + '\n' + meas + '\n.end\n'
    if amp: txt = txt.replace('VAMP AMPIN 0 DC 0', amp, 1)
    for a, b in (repl or {}).items():
        if a.startswith('BOVL') and a not in txt:
            raise SystemExit(f'ТЕСТ-ХУК НЕ ПРИМЕНИЛСЯ (изменилась строка BOVL в мастере): {a}')
        txt = txt.replace(a, b)
    return txt
T = {}
T['TC1_power_on'] = dict(scenario=LOAD_BASE, tran='.tran 20u 8 0 20u uic', meas="""
.meas tran vpin6_off FIND v(PIN6) AT=1
.meas tran vpin6_on  FIND v(PIN6) AT=6
.meas tran iled      FIND i(VLEDS) AT=6
.meas tran vg1 FIND v(GATE1) AT=6
.meas tran vcs FIND v(CS)   AT=6
.meas tran vgs PARAM='vg1-vcs'
.meas tran vsout FIND v(SPK) AT=6
.meas tran vdly_on WHEN v(VDLY)=2.06 RISE=1
""")
OVL_OLD = 'BOVL VOVLX 0 V = { 0.67*(abs(i(VIOUT))/5) }'
OVL_NEW = 'BOVL VOVLX 0 V = { 0.67*(abs(i(VIOUT))/50) }  ; ТЕСТ-ХУК: детектор перегрузки выведен из игры (проверяется в TC5)'
OVL_BYPASS = {OVL_OLD: OVL_NEW}
T['TC2_rds25'] = dict(scenario=LOAD_BASE + "ILOAD 0 SPK DC 10\n", tran='.tran 50u 8 0 50u uic', repl=OVL_BYPASS, meas="""
.meas tran vspk FIND v(SPK) AT=6
.meas tran vamp FIND v(AMP_OUT) AT=6
.meas tran ikey FIND i(VIOUT) AT=6
.meas tran voff_out FIND v(AMP_OUT) AT=6
.meas tran rds_key PARAM='(vspk-vamp)/ikey'
""")
T['TC2b_rds100'] = dict(**{**T['TC2_rds25'], 'temp': 100})
TRIPNODE = "BTRIP TRIP 0 V = { ((v(GATE1)<1)?5:0) }\n"
ACTRIP   = "BACT ACTRIP 0 V = { ((v(VAC4)<0.74)?5:0) }\n"
T['TC3_dc_pos'] = dict(scenario=LOAD_BASE, amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 3)',
  extra_elems=TRIPNODE, tran='.tran 20u 9 0 20u uic', meas="""
.meas tran vn2_pre  FIND v(N2) AT=4.9
.meas tran vn2_post FIND v(N2) AT=6.5
.meas tran t_det WHEN v(VFLT)=2.5 RISE=1
.meas tran t_delay PARAM='t_det-5.0'
.meas tran t_vgs_off WHEN v(GATE1)=2.8 FALL=1
.meas tran t_off PARAM='t_vgs_off-t_det'
.meas tran vflt_end FIND v(VFLT) AT=8.5
.meas tran vlatch_end FIND v(VLATCH) AT=8.5
""")
T['TC4_dc_neg'] = dict(**{**T['TC3_dc_pos'], 'amp': 'VAMP AMPIN 0 PWL(0 0 5 0 5.001 -3)'})
# TC5: перегрузка по выводу 1. Нагрузка низкоомная (0.05 Ом = короткое замыкание),
# амплитуда УМ подаётся ПОСЛЕ power-on (t=5 c). Жёсткий источник тока ILOAD 6 A убран:
# при разомкнутом ключе он заряжал SPK до 48 В и давал ложный бросок при замыкании,
# из-за чего срабатывал детектор и модель «дребезжала». Порог 0.67 В и /5 не менялись.
T['TC5_overload'] = dict(scenario=LOAD_BASE.replace('RLOAD SPKX 0 8', 'RLOAD SPKX 0 0.05'),
  amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 0.4)', tran='.tran 50u 8 0 50u uic', meas="""
.meas tran vg_on  FIND v(GATE1) AT=4.9
.meas tran vcs_on FIND v(CS)    AT=4.9
.meas tran vgs_on PARAM='vg_on-vcs_on'
.meas tran iled_on FIND i(VLEDS) AT=4.9
.meas tran vovl MAX v(VOVL) FROM=5.0 TO=8
.meas tran t_trip WHEN v(VFLT)=2.5 RISE=1
.meas tran vg_off  FIND v(GATE1) AT=7.5
.meas tran vcs_off FIND v(CS)    AT=7.5
.meas tran vgs_off PARAM='vg_off-vcs_off'
.meas tran vlatch FIND v(VLATCH) AT=7.5
.meas tran ikey_pre  FIND i(VIOUT) AT=5.05
.meas tran ikey_off  FIND i(VIOUT) AT=7.5
""")
T['TC6_acoff'] = dict(scenario=LOAD_BASE, tran='.tran 20u 8 0 20u uic', extra_elems=TRIPNODE+ACTRIP,
  repl={'DAC  ACR VACR DRECT':'SAC ACR ACR2 VOPAC 0 SW6\nVOPAC VOPAC 0 PWL(0 5 5 5 5.0005 0)\nDAC  ACR2 VACR DRECT'}, meas="""
.meas tran vac4_before FIND v(VAC4) AT=4.9
.meas tran t_acloss WHEN v(VAC4)=0.74 FALL=1
.meas tran t_out WHEN v(GATE1)=1 FALL=1
.meas tran t_off PARAM='t_out-t_acloss'
""")
T['TC7b_autoreset'] = dict(scenario=LOAD_BASE, amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 3 6.5 3 6.501 0)',
  tran='.tran 20u 9 0 20u uic', repl={'RLEAK VLATCH 0 1G': 'RLEAK VLATCH 0 10k', '.param LATCH_HOLD=1': '.param LATCH_HOLD=0'}, meas="""
.meas tran vg_fault  FIND v(GATE1) AT=6.4
.meas tran vcs_fault FIND v(CS)    AT=6.4
.meas tran vgs_fault PARAM='vg_fault-vcs_fault'
.meas tran vg_after  FIND v(GATE1) AT=8.8
.meas tran vcs_after FIND v(CS)    AT=8.8
.meas tran vgs_after PARAM='vg_after-vcs_after'
.meas tran vlatch_after FIND v(VLATCH) AT=8.8
""")
# TC9: выключение под током (R11/R12). SPEC требует 20 А / 50 В. Нагрузка 2.4 Ом
# (короткое замыкание) и ступень УМ 50 В дают пик ~20.7 А; t_off считается до Vgs=Vto=2.8 В.
T['TC9_soa'] = dict(scenario=LOAD_BASE.replace('RLOAD SPKX 0 8', 'RLOAD SPKX 0 2.4'),
  amp='VAMP AMPIN 0 PWL(0 0 5 0 5.000001 50)',
  extra_elems=("BPWR PWR 0 V = { abs((v(AMP_OUT)-v(SPK))*i(VIOUT)) }\n"
               "* Физический интегратор энергии: 1 мкА на 1 Вт в 1 мкФ -> 1 В на выходе = 1 Дж\n"
               "BINT 0 CINT I = { v(PWR)*1e-6 }\n"
               "CINT CINT 0 1u ic=0\n"), tran='.tran 10u 6 0 10u uic', meas="""
.meas tran ikey0 MAX i(VIOUT) FROM=5.0 TO=5.01
.meas tran t_det WHEN v(VFLT)=2.5 RISE=1
.meas tran t_delay PARAM='t_det-5.0'
.meas tran t_vgs_off WHEN v(GATE1)=2.8 FALL=1
.meas tran t_off PARAM='t_vgs_off-t_det'
.meas tran e_off_info INTEG v(PWR) FROM=5.0 TO=5.2
.meas tran e_int FIND v(CINT) AT=5.2
.meas tran e_analytic PARAM='0.5*50*ikey0*t_off'
""")
T['TC17_speaker_rl_bemf'] = dict(
  scenario=("VSNS SPK SPKX 0\n"
            "RLOAD SPKX SPKX2 6.4\n"          # Re реального 8-омного динамика
            "LLOAD SPKX2 SPKX3 1m\n"          # Le катушки + кабель + выходной дроссель УМ
            "VBEMF SPKX3 0 PWL(0 0 5.0007 0 5.0008 40 5.002 40 5.0021 0)\n"),
  amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 50)',
  repl={'DTVS1 CS AMP_OUT DTVS': 'VTVS CS CSM 0\nDTVS1 CSM AMP_OUT DTVS\nDTVS2 CSM SPK DTVS', 'DTVS2 CS SPK DTVS': '*DTVS2 CS SPK DTVS (перенесён в repl выше)'},
  extra_elems=("BT_PWR TPWR 0 V = { abs(v(VSW)*i(VTVS)) }\n"
               "* Физический интегратор энергии ограничителя: 1 мкА на 1 Вт в 1 мкФ -> 1 В = 1 Дж\n"
               "BINT 0 CINT I = { v(TPWR)*1e-6 }\n"
               "CINT CINT 0 1u ic=0\n"),
  tran='.tran 5u 6 0 5u uic', meas="""
.meas tran ikey0  MAX i(VIOUT) FROM=5.0 TO=5.01
.meas tran t_det   WHEN v(VFLT)=2.5 RISE=1
.meas tran vsw_pk  MAX v(VSW) FROM=5.0 TO=5.2
.meas tran vsw_pk2 MAX v(VSW) FROM=5.0007 TO=5.003
.meas tran e_clamp FIND v(CINT) AT=5.2
.meas tran itvs_pk MAX i(VTVS) FROM=5.0 TO=5.2
""")
T['TC18_blocking'] = dict(
  scenario=LOAD_BASE, amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 50 5.5 50 5.501 -50)',
  tran='.tran 20u 9 0 20u uic', meas="""
.meas tran vsw_pos FIND v(VSW) AT=5.4
.meas tran ileak_pos FIND i(VIOUT) AT=5.4
.meas tran vsw_neg FIND v(VSW) AT=5.7
.meas tran ileak_neg FIND i(VIOUT) AT=5.7
.meas tran vlatch_end FIND v(VLATCH) AT=8.5
""")
T['TC13a_ind_load'] = dict(
  scenario="VSNS SPK SPKX 0\nRLOAD SPKX SPKX2 2.4\nLLOAD SPKX2 0 0.5m\n",
  amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 50)', tran='.tran 10u 6 0 10u uic',
  meas="""
.meas tran ikey0  MAX i(VIOUT) FROM=5.0 TO=5.01
.meas tran t_det   WHEN v(VFLT)=2.5 RISE=1
.meas tran t_vgs_off WHEN v(GATE1)=2.8 FALL=1
.meas tran t_off   PARAM='t_vgs_off-t_det'
.meas tran vsw_pk  MAX v(VSW) FROM=5.0 TO=5.2
.meas tran vsw_pk_t MAX v(VSW) FROM=5.0001 TO=5.005
.meas tran vsw_late MAX v(VSW) FROM=5.005 TO=5.2
""")
T['TC13b_ind_dead_amp'] = dict(
  scenario="VSNS SPK SPKX 0\nRLOAD SPKX SPKX2 2.4\nLLOAD SPKX2 0 0.5m\nRDAMP AMP_OUT 0 1k\n",
  amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 50)', tran='.tran 10u 6 0 10u uic',
  repl={'ROUT AMPIN ROUTX 10m': 'ROUT AMPIN ROUTX 10m\n* выходной каскад УМ «мертв»: импеданс выхода 1 кОм (RDAMP) вместо 10 мОм',
},
  meas="""
.meas tran vsw_pk  MAX v(VSW) FROM=5.0 TO=5.2
.meas tran vgs_off FIND v(GATE1) AT=5.05
""")
T['TC14_vcc60'] = dict(scenario=LOAD_BASE, tran='.tran 20u 8 0 20u uic',
  repl={'VCC45 VCC45 0 45': 'VCC45 VCC45 0 60', '.param R08=15k': '.param R08=20k'},
  meas="""
.meas tran vic   FIND v(VCCIC) AT=6
.meas tran vdly_on WHEN v(VDLY)=2.06 RISE=1
.meas tran iled  FIND i(VLEDS) AT=6
.meas tran vgs   FIND v(GATE1) AT=6
.meas tran vlogic FIND v(LOGIC) AT=6
""")
T['TC15_vcc25'] = dict(scenario=LOAD_BASE, tran='.tran 20u 8 0 20u uic',
  repl={'VCC45 VCC45 0 45': 'VCC45 VCC45 0 25', '.param R08=15k': '.param R08=7.5k'},
  meas="""
.meas tran vic   FIND v(VCCIC) AT=6
.meas tran vdly_on WHEN v(VDLY)=2.06 RISE=1
.meas tran iled  FIND i(VLEDS) AT=6
.meas tran vgs   FIND v(GATE1) AT=6
.meas tran vlogic FIND v(LOGIC) AT=6
""")
T['TC16_dc_trip_vcc60'] = dict(scenario=LOAD_BASE, amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 3)',
  tran='.tran 20u 9 0 20u uic', repl={'VCC45 VCC45 0 45': 'VCC45 VCC45 0 60', '.param R08=15k': '.param R08=20k'}, meas="""
.meas tran t_det WHEN v(VFLT)=2.5 RISE=1
.meas tran t_delay PARAM='t_det-5.0'
.meas tran vlatch_end FIND v(VLATCH) AT=8.5
.meas tran t_vgs_off WHEN v(GATE1)=2.8 FALL=1
.meas tran t_off PARAM='t_vgs_off-t_det'
""")
T['TC7a_latch'] = dict(scenario=LOAD_BASE, amp='VAMP AMPIN 0 PWL(0 0 5 0 5.001 3 6.5 3 6.501 0)',
  tran='.tran 20u 9 0 20u uic', meas="""
* Vgs измеряется ДИФФЕРЕНЦИАЛЬНО: в закрытом состоянии вся вторичная сторона (VIOP/VION/CS/GATE)
* плавает, и абсолютное v(GATE1) не имеет смысла (может быть -1 В при полностью закрытом ключе).
.meas tran vg_fault FIND v(GATE1) AT=6.0
.meas tran vcs_fault FIND v(CS) AT=6.0
.meas tran vgs_fault PARAM='vg_fault-vcs_fault'
.meas tran vg_after FIND v(GATE1) AT=8.8
.meas tran vcs_after FIND v(CS) AT=8.8
.meas tran vgs_after PARAM='vg_after-vcs_after'
.meas tran vlatch_after FIND v(VLATCH) AT=8.8
""")
T['TC8_signal8'] = dict(scenario=LOAD_BASE, amp='VAMP AMPIN 0 SIN(0 20 1000)',
  tran='.tran 10u 6.5 0 10u uic', meas="""
.meas tran vpk_amp MAX v(AMP_OUT) FROM=6.0 TO=6.001
.meas tran vpk_spk MAX v(SPK) FROM=6.0 TO=6.001
.meas tran imax MAX i(VIOUT) FROM=6.0 TO=6.001
.meas tran vzc FIND v(SPK) AT=6.0005
.meas tran loss_db PARAM='20*log10(vpk_spk/vpk_amp)'
.meas tran rds_dyn PARAM='abs(vpk_amp-vpk_spk)/abs(imax)'
""")
T['TC8b_signal4'] = dict(scenario=LOAD_BASE.replace('RLOAD SPKX 0 8', 'RLOAD SPKX 0 4'),
  amp='VAMP AMPIN 0 SIN(0 15 1000)', tran='.tran 10u 6.5 0 10u uic', meas="""
.meas tran vpk_amp MAX v(AMP_OUT) FROM=6.0 TO=6.001
.meas tran vpk_spk MAX v(SPK) FROM=6.0 TO=6.001
.meas tran imax MAX i(VIOUT) FROM=6.0 TO=6.001
.meas tran vzc FIND v(SPK) AT=6.0005
.meas tran loss_db PARAM='20*log10(vpk_spk/vpk_amp)'
.meas tran rds_dyn PARAM='abs(vpk_amp-vpk_spk)/abs(imax)'
""")
T['TC10_failsafe'] = dict(scenario=LOAD_BASE, tran='.tran 20u 9 0 20u uic',
  extra_elems='VOPEN VOP 0 PWL(0 5 5 5 5.0005 0)\n',
  repl={'RLED VHLOG LED_A {RLIM}': 'RLED VHLOG LED_A0 {RLIM}\nSOPEN LED_A0 LED_A VOP 0 SW6'}, meas="""
.meas tran vg_before  FIND v(GATE1) AT=4.9
.meas tran vcs_before FIND v(CS)    AT=4.9
.meas tran vgs_before PARAM='vg_before-vcs_before'
.meas tran vg_after   FIND v(GATE1) AT=8.5
.meas tran vcs_after  FIND v(CS)    AT=8.5
.meas tran vgs_after  PARAM='vg_after-vcs_after'
.meas tran vspk_after FIND v(SPK) AT=8.5
.meas tran iled_after FIND i(VLEDS) AT=8.5
""")
T['TC11_worstcase'] = dict(scenario=LOAD_BASE + "ILOAD 0 SPK DC 10\n", tran='.tran 50u 8 0 50u uic', temp=100,
  repl={**OVL_BYPASS, 'VOC=8.4': 'VOC=7.8'}, meas="""
.meas tran vspk FIND v(SPK) AT=6
.meas tran vamp FIND v(AMP_OUT) AT=6
.meas tran ikey FIND i(VIOUT) AT=6
.meas tran vg_x  FIND v(GATE1) AT=6
.meas tran vcs_x FIND v(CS)    AT=6
.meas tran vgs_x PARAM='vg_x-vcs_x'
.meas tran rds_key PARAM='abs((vspk-vamp)/ikey)'
.meas tran rds_each PARAM='abs((vspk-vamp)/ikey)/2'
""")
# TC12: подача питания при постоянной аварии. Авария задана с запасом над порогом DC +Vth~1.99 В
# (VAMP=3 В -> N2=0.935 В > 0.62 В), а не ровно на пороге (2 В -> N2=0.623 В): на границе BS1
# «дребезжит», и .tran теряет сходимость. Vgs считается как v(GATE1)-v(CS).
T['TC12_hot_start'] = dict(scenario=LOAD_BASE, amp='VAMP AMPIN 0 DC 3', tran='.tran 20u 8 0 20u uic', meas="""
.meas tran vg_max  MAX v(GATE1) FROM=4.5 TO=8
.meas tran vcs_min MIN v(CS)    FROM=4.5 TO=8
.meas tran vgs_max PARAM='vg_max-vcs_min'
.meas tran vlatch  FIND v(VLATCH) AT=7.5
""")
out = os.path.join(ROOT, 'tests'); os.makedirs(out, exist_ok=True)
for n, c in T.items():
    open(os.path.join(out, n + '.cir'), 'w', encoding='utf-8').write(build(**c))
    print('written', n)

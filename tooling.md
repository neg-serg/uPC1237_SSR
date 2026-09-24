# LTspice netlist verification

## 1. ngspice availability (nix/apt/pip)
`ngspice` is not preinstalled. `apt-get` is absent (NixOS); `python3 -m pip` gives `No module named pip`.
Nix works:
```
$ nix shell nixpkgs#ngspice -c ngspice --version          # exit 0
this path will be fetched (3.2 MiB ...): /nix/store/...-ngspice-45
** ngspice-45 : Circuit level simulation program
```
=> nix: yes; apt/pip: no.

## 2. LTspice `.model X VDMOS(... Ron=10m ...)`
It parses without error or warning, but `Ron` is silently NOT applied. Measured Rds(on)=Vd/Id, only the model card changed:
| card | measured Rds |
|---|---|
| `Ron=10m` | 8.40336e-03 |
| `Ron=100` | 8.40336e-03 |
| no `Ron` | 8.40336e-03 |
| `Rd=0.01` | 1.836509e-02 |
| `Rds=0.01` | 4.566210e-03 |
So use ngspice-native series `Rd`/`Rs`, not `Ron`. LTspice diode `D(Ron=1m Roff=1Meg)` prints
`Warning: Model issue ... unrecognized parameter (ron) - ignored` (and `roff`).

## 3. LTspice IV constructs vs ngspice-45
Incompatible:
- `.step param ...` -> `Error: ... unimplemented dot command '.step'`, exit 1.
- `.meas ... TRIG v(g)=1 RISE=1` -> `no such vector as 'v(g)=1'`; only `TRIG v(g) VAL=1` works.
- `.meas ... FIND abs(i(vd))` -> `no such vector as abs(i(vd))`; `FIND` takes a plain vector.
- `.meas ... PARAM='abs(v(d)/i(vd))'` -> `Undefined parameter [v]`, `failed`; `PARAM` must reference named measurement scalars (`PARAM='abs(vds/id)'` works).
- VDMOS `Ron=` ignored; diode `Ron=`/`Roff=` ignored (see §2).

Compatible: `PULSE(...)`, `.tran ... uic`, B-sources (`B1 n 0 V = ...`), `D` + VDMOS in one netlist, `.op`/`.print`.
In batch mode an output directive (`.print`/`.plot`/`.meas`) is mandatory, otherwise exit 1 "no simulations run".

## 4. Working example and actual output
`/tmp/ssr-prot/test_rds.cir`:
```
* Rds(on) of an open VDMOS, LTspice-style card
Vg g 0 10
Vd d 0 0.1
M1 d g 0 0 DMOS
.model DMOS VDMOS(Ron=10m Vto=4 Kp=20 Cgs=2n Cgdmax=1n)
.tran 10n 10u uic
.meas tran vds FIND v(d) AT=5u
.meas tran id  FIND i(Vd) AT=5u
.meas tran rds_on PARAM='abs(vds/id)'
.end
```
```
$ nix shell nixpkgs#ngspice -c ngspice -b test_rds.cir        # exit 0
Measurements for Transient Analysis
vds     =  1.000000e-01
id      = -1.190000e+01
rds_on  =  8.40336e-03
```
8.4 mOhm is channel-only: `Ron=10m` added nothing. Add series resistance natively with `Rd`/`Rs` (`Rd=10m` -> 18.4 mOhm total).

## 5. LTspice / wine
`wine --version` -> `wine-11.0`. LTspice is NOT installed: `wineapps list` -> `no apps declared`; no `LTspice.exe`/`XVIIx64.exe` found. nixpkgs contains an `ltspice` recipe but it is not installed. No GUI/wine install was performed.

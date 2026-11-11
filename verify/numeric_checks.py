"""Second, independent check for every computational question: plain arithmetic, no model.

The triage engine never changes an answer key on one opinion. A key change needs a blind model solve
AND this script (or a second blind solve in live mode) to land on the same value.
Run: python3 verify/numeric_checks.py  ->  verify/numeric_checks.json
"""
import json
import math
import os

h, m_e, e, eps0 = 6.626e-34, 9.109e-31, 1.602e-19, 8.854e-12
C = {}


def put(qid, value, option, note):
    C[qid] = {"value": value, "answer": option, "note": note}


# LCR supply voltage
put("60f744b3f1b9bc7cc7b4a949", math.hypot(40, 60 - 30), "A", "sqrt(VR^2 + (VL-VC)^2) = 50 V")
# kinetic theory pressure
put("68e870ef42c06737d6e565c4", 9e-2 * 400**2 / 3, "D", "P = rho v^2 / 3 = 4800 N/m^2")
# flux through cube: q/2 at face centre (half inside), 2q at corner (one eighth inside); flux = n q / (2 eps0)
put("68dea616d0cda73d07e93ae6", (0.5 * 0.5 + 2 / 8) * 2, "1", "(q/4 + q/4)/eps0 = q/(2 eps0) so n = 1")
# copper cube, edge 10 cm (value taken from the stored solution)
put("696a866665252c04fc1f81c2", 7e6 / 1.4e11 * 0.1**3 * 1e9, "50", "dV = P V / B with a = 10 cm gives 50 mm^3")
# series RL impedance with L = 95.5 mH (value taken from the stored solution)
put("60f742f6660d187cc13a8078", math.hypot(40, 2 * math.pi * 50 * 95.5e-3), "C", "Z = sqrt(40^2 + (2 pi 50 L)^2) = 50 ohm")
# centre of mass velocity
put("622f08d7b70e4b50e4500a1b", (10 * 14 + 4 * 0) / 14, "C", "v_cm = 140/14 = 10 m/s")
# ratio of coulomb forces on the two charges
put("68e872546e45ba37dcc16bc0", 1.0, "C", "Newton's third law: equal magnitudes, ratio 1:1 (the blank option)")
# radioactive: 7/8 decays -> 3 half lives
put("63765a28f1d8416ae0408d89", 60 * math.log2(8), "C", "3 half-lives = 180 days")
# AC power with 90 degree phase
put("6956d79788d7701e5617bc29", (5 / math.sqrt(2)) * (200 / math.sqrt(2)) * math.cos(math.pi / 2), "B", "P = Vrms Irms cos 90 = 0 W (options B and C both say 0 W)")
# floating cube: 800 g = 2 cm * a^2 * 1 g/cm^3
put("6263d75bdd44e265ef926d97", math.sqrt(800 / 2), "20", "a^2 = 400 so a = 20 cm; the stored solution's last line says 40")
# electron KE for de Broglie wavelength 0.3 nm
put("612151a6a34397610a9a2e58", h**2 / (2 * m_e * (0.3e-9) ** 2) / e, "B", "K = h^2/(2 m lambda^2) = 16.7 eV")
# mean life
put("68f21caf941cda588bc04365", 3 / math.log(8), "B", "tau = t / ln 8 = 1.44 min; exactly one option is right")
# wall friction
put("5fc60508028950133eac8963", min(0.3 * 100, 2 * 10), "20", "f = mg = 20 N (< mu N = 30 N), with g = 10")
# silver rod cubical expansion
put("6062ec84518e9535e120c422", 3 * 0.19 / (100 * 100) * 1e5, "A", "gamma = 3 alpha = 5.7 x 1e-5 per degC")
# projectile R = H  ->  tan(theta) = 4
put("6956d7bb23cb221e570d6013", 4.0, "B", "sin^2/2 = 2 sin cos so tan(theta) = 4")
# block on rough floor, weight 100 N (m = 10 kg): F - 100mu = 10 ; 2F - 100mu = 100
F = 100 - 10
put("68e8734442c06737d6e56da4", (F - 10) / 100, "A", "F = 90 N, mu = 0.8")
# SHM from mean position, T = 16 s, v(2 s) = pi
w = 2 * math.pi / 16
put("6956d7e988d7701e5617bd3e", math.pi / (w * math.cos(w * 2)) / math.sqrt(2), "D", "A = 8 sqrt2 m (value shown is A/sqrt2 = 8)")
# two wheels: relative angle 2 pi
put("68dea619d0cda73d07e93aee", math.sqrt(2 * math.pi / (0.5 * (math.pi / 2 - math.pi / 4))), "4", "0.5 (pi/4) t^2 = 2 pi so t = 4 s")
# YDSE shift in cm
put("68dea7c2387eea3d0d95f9bb", (1 / 5e-3) * (2e-3 * 0.5 - 1.5e-3 * 0.4) * 100, "8", "0.08 m = 8 cm")
# significant figures
put("68dea715387eea3d0d95f790", round(6 * 7.203**2, 1) * 10, "3113", "311.299 -> 311.3 (4 s.f.), 10A = 3113")
# interference, equal amplitudes, phase pi/2: I / I0
put("695ee00b88d7701e561aabc5", 1 + 1 + 2 * math.cos(math.pi / 2), "none", "I = 2 I0, so Assertion is false; Reason ('always the sum') is false too. No option says both false.")
# charges changed by +10% / -10%
put("60ca4feb6420652745f55522", 100 * 1.1 * 0.9, "C", "99 N")
# stopping potential
put("68c9ae5afb6b2f16e2d43b1c", 12400 / 4000 - 2.0, "D", "3.1 eV - 2.0 eV = 1.1 V")
# KE x4 -> momentum x2
put("68f21df0941cda588bc0470b", math.sqrt(4), "A", "p scales as sqrt(KE)")
# electron KE with de Broglie wavelength = lambda_min of 24.8 kV tube
lam = 6.6e-34 * 3e8 / (1.6e-19 * 24800)
put("68c801bc1b1dbc16dc93bf2b", (6.6e-34) ** 2 / (2 * 9.1e-31 * lam**2) / 1.6e-19, "A", "about 600 eV")
# displacement current
put("63c7cce12981ed154ee92c94", 10 * eps0 * 1 / 1e-3 * 25 * 1e6, "C", "C dV/dt = 2.2 microamp")
# 64 drops: sigma ratio
put("636283dbe3770c24f866e6d6", 64 / 4**2, "B", "Q x64, area x16, ratio 4:1")
# uniformly charged sphere, surface potential 16 V
V = 16
put("68dea577d0cda73d07e9391c", V * (3 - 0.25) / 2 - V / 2, "14", "V_P = 22 V, V_S = 8 V, difference 14 V")
# K = alpha V capacitor: V^2 + V - 30 = 0
put("68dea87d387eea3d0d95fbe3", (-1 + math.sqrt(1 + 120)) / 2, "A", "V = 5 V")
# two lenses in contact, m = -4, u = -12.5 cm
feq = 1 / (1 / 50 + 1 / 12.5)
put("68dea657387eea3d0d95f54a", (100 / feq) / 2, "5", "f_eq = 10 cm, 10 D total, 5 D each")
# displacement method
x = math.sqrt(150 * (150 - 4 * 24))
put("68dea6e6387eea3d0d95f6f8", ((150 + x) / (150 - x)) ** 2, "16", "x = 90 cm, ratio 16")

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "numeric_checks.json")
    for v in C.values():
        v["value"] = round(v["value"], 4)
    json.dump(C, open(out, "w", encoding="utf-8"), indent=1)
    for k, v in C.items():
        print(k, v["value"], "->", v["answer"], "|", v["note"])

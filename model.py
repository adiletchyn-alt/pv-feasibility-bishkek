"""
Feasibility model for a rooftop PV plant on a business centre in Bishkek.
Three options on Huawei FusionSolar equipment.

Run:  python model.py        -> prints results and writes results.json
All assumptions are in the ASSUMPTIONS block; sources for facts are in the README.
"""
import json
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# ASSUMPTIONS (fact = verified source, assum. = author's assumption)
# ---------------------------------------------------------------------------
A = dict(
    year0=2026,                 # investment year; operation from 2027
    horizon=25,                 # project life, years (assum.)
    fx_som_usd=87.45,           # exchange rate, KGS per USD (fact, 24.kg, 2026)
    tariff_som=4.33,            # commercial tariff from 01.05.2026, excl. taxes (fact)
    export_som=1.45,            # surplus buy-back price (assum.: household rate 2026)
    esc_to_2030=0.08,           # tariff growth per year to 2030 (assum.; official +20%/yr schedule is stated for households)
    esc_after=0.05,             # tariff growth after 2030 (assum.)
    opex_infl=0.05,             # O&M cost inflation (assum.)
    discount=0.14,              # discount rate, nominal in KGS (assum.: National Bank policy rate 12% + 2 pp)
    tax=0.10,                   # profit tax (assum., check against the Tax Code)
    dep_years=10,               # depreciation period (assum.)
    tax_holiday=0,              # years of profit-tax exemption from commissioning (incentive scenario; 0 = none)
    yield_kwh_kwp=1500,         # specific yield, kWh/kWp per year (assum.; GSA 1484 / PVGIS 1681 from a Tazabek search snippet)
    degr=0.004,                 # module degradation per year (assum.)
    load_kwh=250_000,           # annual building consumption (assum., calibrated to Orion-2)
    batt_rte=0.913,             # LUNA2000-215 round-trip efficiency (fact, Huawei datasheet)
    batt_reserve=0.30,          # capacity reserved for backup power (assum.)
    batt_degr=0.02,             # capacity loss per year (assum.)
)

# Seasonal PV output, kWh/day per kW (fact: profileSOLAR / NASA POWER)
SEASON = {"winter": 2.56, "spring": 5.72, "summer": 6.95, "autumn": 4.09}

# ---------------------------------------------------------------------------
# Equipment & CAPEX, USD (prices: see README; most are assumptions)
# ---------------------------------------------------------------------------
P = dict(
    module_usd_w=0.22,          # TOPCon 580 W, wholesale delivered (assum.; Bishkek retail ~$0.30/W)
    inv50_usd=3400,             # SUN2000-50KTL-M3 (benchmark: Combishop NL EUR 3,564 incl. VAT = ~$3,300-3,450 excl. VAT)
    smartlogger_meter_usd=1000, # SmartLogger3000A + DTSU666-HW (assum.)
    luna215_usd=64000,          # LUNA2000-215-2S10 (benchmark: EU EUR 50-80k, incl./excl. VAT)
    logistics=0.10,             # logistics and customs on imports (assum.)
    bos_usd_w=0.15,             # ballast, cabling, protection, SPD, grounding (assum.)
    install_usd_w=0.12,         # design, installation, commissioning (assum.)
    survey_usd=1500,            # roof survey (assum.)
    ats_usd=5000,               # ATS / island-mode switchboard (assum.)
    batt_install_usd=3000,      # battery foundation and connection (assum.)
    license_usd=2000,           # licence, bidirectional meter, contract (assum.)
    contingency=0.07,           # contingency (assum.)
    om_pv=0.01,                 # PV O&M, share of CAPEX per year (assum.)
    om_batt=0.005,              # battery O&M (assum.)
    inv_replace_year=12,        # inverter replacement year (assum.)
    batt_replace_year=13,       # battery replacement year (assum.)
    batt_replace_share=0.60,    # replacement cost vs today's price (assum.)
)

MODULE_W = 580
STRING_LEN = 15

VARIANTS = {
    "V1": dict(name="Grid-tied 61 kWp, zero export", strings=7, inverters=1,
               battery=False, export=False),
    "V2": dict(name="Hybrid 61 kWp + 215 kWh battery", strings=7, inverters=1,
               battery=True, export=False),
    "V3": dict(name="Grid-tied 122 kWp, surplus export", strings=14, inverters=2,
               battery=False, export=True),
}


# ---------------------------------------------------------------------------
# Hourly profiles (typical average day per month)
# ---------------------------------------------------------------------------
def monthly_pv_per_kwp(annual=None):
    """Monthly kWh/kWp: seasonal values placed at Jan/Apr/Jul/Oct, interpolated, scaled."""
    centers = {1: SEASON["winter"], 4: SEASON["spring"], 7: SEASON["summer"], 10: SEASON["autumn"]}
    xs = [1, 4, 7, 10, 13]
    ys = [centers[1], centers[4], centers[7], centers[10], centers[1]]
    daily = np.interp(np.arange(1, 13), xs, ys)
    days = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    raw = daily * days
    annual = A["yield_kwh_kwp"] if annual is None else annual
    return raw / raw.sum() * annual, days


def daylight_hours(month, lat=42.87):
    doy = 30.4 * (month - 1) + 15
    decl = 23.44 * np.sin(np.radians(360 / 365 * (doy - 81)))
    cosw = -np.tan(np.radians(lat)) * np.tan(np.radians(decl))
    return 2 * np.degrees(np.arccos(np.clip(cosw, -1, 1))) / 15


def pv_hourly_shape(month):
    """24-h shape (sums to 1), solar noon ~13:00 local (UTC+6, lon 74.6E)."""
    dl = daylight_hours(month)
    noon = 13.0
    h = np.arange(24) + 0.5
    s = np.cos(np.pi * (h - noon) / dl)
    s[np.abs(h - noon) > dl / 2] = 0
    s = np.clip(s, 0, None) ** 1.3
    return s / s.sum()


SEASON_LOAD = [1.05, 1.00, 0.90, 0.85, 0.90, 1.10, 1.20, 1.20, 1.00, 0.90, 0.95, 1.05]


def load_day(kind):
    """Relative hourly load: weekday / saturday / sunday for an office centre."""
    base = 0.35
    d = np.full(24, base)
    if kind == "weekday":
        d[7], d[20] = 0.6, 0.6
        d[8:20] = 1.0
    elif kind == "saturday":
        d[9:15] = 0.6
    return d


def build_year():
    """Return DataFrame of 8760 hours with relative load and PV per kWp."""
    pv_m, days = monthly_pv_per_kwp()
    rows = []
    dates = pd.date_range("2027-01-01", periods=365, freq="D")
    for d in dates:
        m = d.month
        kind = "weekday" if d.weekday() < 5 else ("saturday" if d.weekday() == 5 else "sunday")
        pv = pv_hourly_shape(m) * pv_m[m - 1] / days[m - 1]
        ld = load_day(kind) * SEASON_LOAD[m - 1]
        for hh in range(24):
            rows.append((d, m, hh, pv[hh], ld[hh]))
    df = pd.DataFrame(rows, columns=["date", "month", "hour", "pv_kwp", "load_rel"])
    df["load"] = df["load_rel"] / df["load_rel"].sum() * A["load_kwh"]
    return df


# ---------------------------------------------------------------------------
# Energy balance
# ---------------------------------------------------------------------------
def simulate(df, kwp, inv_kw, battery=False, cap_kwh=215.0, p_kw=108.0):
    pv = np.minimum(df["pv_kwp"].values * kwp, inv_kw)   # AC clipping
    load = df["load"].values
    n = len(pv)
    direct = np.minimum(pv, load)
    surplus = pv - direct
    deficit = load - direct
    from_batt = np.zeros(n)
    to_batt = np.zeros(n)
    if battery:
        eta = np.sqrt(A["batt_rte"])
        soc_min = cap_kwh * A["batt_reserve"]
        soc = soc_min
        for i in range(n):
            if surplus[i] > 0:
                c = min(surplus[i], p_kw, (cap_kwh - soc) / eta)
                soc += c * eta
                to_batt[i] = c
            elif deficit[i] > 0:
                d = min(deficit[i], p_kw, (soc - soc_min) * eta)
                soc -= d / eta
                from_batt[i] = d
    spill = surplus - to_batt
    return dict(
        pv=pv.sum(), load=load.sum(), direct=direct.sum(), from_batt=from_batt.sum(),
        spill=spill.sum(),
        self_used=direct.sum() + from_batt.sum(),
        monthly_pv=pd.Series(pv).groupby(df["month"].values).sum().round(0).tolist(),
        monthly_self=pd.Series(direct + from_batt).groupby(df["month"].values).sum().round(0).tolist(),
    )


# ---------------------------------------------------------------------------
# CAPEX
# ---------------------------------------------------------------------------
def capex(v):
    kwp = v["strings"] * STRING_LEN * MODULE_W / 1000
    w = kwp * 1000
    equip = w * P["module_usd_w"] + v["inverters"] * P["inv50_usd"] + P["smartlogger_meter_usd"]
    items = {
        "Modules": w * P["module_usd_w"] * (1 + P["logistics"]),
        "Inverters SUN2000-50KTL-M3": v["inverters"] * P["inv50_usd"] * (1 + P["logistics"]),
        "SmartLogger + meter": P["smartlogger_meter_usd"] * (1 + P["logistics"]),
        "BOS (mounting, cabling, protection)": w * P["bos_usd_w"],
        "Design, installation, commissioning": w * P["install_usd_w"],
        "Roof survey": P["survey_usd"],
    }
    if v["battery"]:
        items["Battery LUNA2000-215-2S10"] = P["luna215_usd"] * (1 + P["logistics"])
        items["ATS, island-mode switchboard"] = P["ats_usd"]
        items["Battery installation"] = P["batt_install_usd"]
    if v["export"]:
        items["Licence, bidirectional meter, contract"] = P["license_usd"]
    sub = sum(items.values())
    items["Contingency 7%"] = sub * P["contingency"]
    total = sum(items.values())
    return kwp, {k: round(x) for k, x in items.items()}, total


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------
def irr(cf):
    lo, hi = -0.99, 1.0
    f = lambda r: sum(c / (1 + r) ** t for t, c in enumerate(cf))
    if f(lo) * f(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return mid


def tariff_path(base, esc1, esc2, years, y0):
    out = []
    t = base
    for k in range(1, years + 1):
        y = y0 + k
        t *= (1 + (esc1 if y <= 2030 else esc2))
        out.append(t)
    return out


def finance(v, en, capex_usd, kwp, a=A, extra_value_som=0.0):
    fx = a["fx_som_usd"]
    capex_som = capex_usd * fx
    H = a["horizon"]
    tar = tariff_path(a["tariff_som"], a["esc_to_2030"], a["esc_after"], H, a["year0"])
    exp_p = tariff_path(a["export_som"], a["esc_to_2030"], a["esc_after"], H, a["year0"])
    pv_capex = capex_usd - (P["luna215_usd"] * (1 + P["logistics"]) + P["ats_usd"] + P["batt_install_usd"]
                            if v["battery"] else 0)
    cf = [-capex_som]
    rows = []
    dep = capex_som / a["dep_years"]
    for k in range(1, H + 1):
        pvf = (1 - a["degr"]) ** (k - 1)
        bf = (1 - a["batt_degr"]) ** ((k - 1) % (P["batt_replace_year"]))
        direct = en["direct"] * pvf
        fb = en["from_batt"] * pvf * bf
        spill = en["pv"] * pvf - direct - fb
        savings = (direct + fb) * tar[k - 1]
        export_rev = spill * exp_p[k - 1] if v["export"] else 0.0
        infl = (1 + a["opex_infl"]) ** (k - 1)
        om = (pv_capex * P["om_pv"] + (P["luna215_usd"] * P["om_batt"] if v["battery"] else 0)) * fx * infl
        repl = 0.0
        if k == P["inv_replace_year"]:
            repl += v["inverters"] * P["inv50_usd"] * fx * infl
        if v["battery"] and k == P["batt_replace_year"]:
            repl += P["luna215_usd"] * P["batt_replace_share"] * fx * infl
        extra = extra_value_som * infl
        ebitda = savings + export_rev + extra - om
        taxable = ebitda - (dep if k <= a["dep_years"] else 0) - repl
        tax = 0.0 if k <= a.get("tax_holiday", 0) else max(taxable, 0) * a["tax"]
        net = ebitda - repl - tax
        cf.append(net)
        rows.append(dict(year=a["year0"] + k, tariff=round(tar[k - 1], 2), self_kwh=round(direct + fb),
                         export_kwh=round(spill) if v["export"] else 0, savings=round(savings),
                         export_rev=round(export_rev), om=round(om), repl=round(repl), tax=round(tax),
                         net=round(net)))
    r = a["discount"]
    disc = [c / (1 + r) ** t for t, c in enumerate(cf)]
    npv = sum(disc)
    cum, dcum, pb, dpb = 0, 0, None, None
    for t, (c, d) in enumerate(zip(cf, disc)):
        prev, dprev = cum, dcum
        cum += c
        dcum += d
        if pb is None and t > 0 and cum >= 0:
            pb = t - 1 + (-prev / c)
        if dpb is None and t > 0 and dcum >= 0:
            dpb = t - 1 + (-dprev / d)
    # LCOE: discounted lifetime costs / discounted energy produced
    cost_pv = capex_som + sum((rw["om"] + rw["repl"]) / (1 + r) ** (i + 1) for i, rw in enumerate(rows))
    e_pv = sum(en["pv"] * (1 - a["degr"]) ** i / (1 + r) ** (i + 1) for i in range(H))
    e_used = sum((rw["self_kwh"] + rw["export_kwh"]) / (1 + r) ** (i + 1) for i, rw in enumerate(rows))
    pv_benefits = sum(disc[1:])
    # levelized grid tariff the project competes with (same discounting)
    lev_tariff = sum(t * en["pv"] * (1 - a["degr"]) ** i / (1 + r) ** (i + 1) for i, t in enumerate(tar)) / e_pv
    return dict(
        capex_som=round(capex_som), npv_som=round(npv), irr=irr(cf),
        payback=pb, dpayback=dpb,
        roi=(sum(cf[1:]) - capex_som) / capex_som,
        pi=pv_benefits / capex_som,
        lcoe_gen=cost_pv / e_pv, lcoe_used=cost_pv / e_used, lev_tariff=lev_tariff,
        yr1_net=rows[0]["net"], rows=rows, cf=[round(c) for c in cf],
    )


def breakeven_extra(v, en, cap, kwp):
    """Annual extra value (som, year-1 prices) that brings NPV to zero (e.g. value of backup power)."""
    lo, hi = 0.0, 5e7
    for _ in range(100):
        mid = (lo + hi) / 2
        if finance(v, en, cap, kwp, extra_value_som=mid)["npv_som"] < 0:
            lo = mid
        else:
            hi = mid
    return mid


def run(a_over=None, p_over=None, quiet=True):
    a = dict(A, **(a_over or {}))
    saved_A, saved_P = dict(A), dict(P)
    A.update(a)
    P.update(p_over or {})
    try:
        df = build_year()
        out = {}
        for key, v in VARIANTS.items():
            kwp, items, cap = capex(v)
            en = simulate(df, kwp, 50.0 * v["inverters"], battery=v["battery"])
            fin = finance(v, en, cap, kwp, a)
            out[key] = dict(variant=v, kwp=kwp, capex_items=items, capex_usd=round(cap),
                            usd_per_kwp=round(cap / kwp), energy={k: (round(x) if isinstance(x, float) else x)
                                                                  for k, x in en.items()}, fin=fin)
        return out
    finally:
        A.clear(); A.update(saved_A)
        P.clear(); P.update(saved_P)


if __name__ == "__main__":
    res = run()
    df = build_year()
    for k, r in res.items():
        e, f = r["energy"], r["fin"]
        print(f"\n{k} {r['variant']['name']}  {r['kwp']:.1f} kWp  CAPEX ${r['capex_usd']:,} (${r['usd_per_kwp']}/kWp)")
        print(f"  PV {e['pv']:,} kWh | self {e['self_used']:,} ({e['self_used']/e['pv']:.0%}) | "
              f"spill/export {e['spill']:,} | covers {e['self_used']/e['load']:.0%} of load")
        print(f"  NPV {f['npv_som']/1e6:,.2f} M som (${f['npv_som']/A['fx_som_usd']:,.0f}) | IRR {f['irr']:.1%} | "
              f"PB {f['payback'] and round(f['payback'],1)} | DPB {f['dpayback'] and round(f['dpayback'],1)} | ROI {f['roi']:.0%} | PI {f['pi']:.2f} | "
              f"LCOE {f['lcoe_gen']:.2f} som/kWh gen, {f['lcoe_used']:.2f} used, lev.tariff {f['lev_tariff']:.2f} | yr1 net {f['yr1_net']:,}")
    # breakeven backup value for V2
    v2 = VARIANTS["V2"]
    kwp, _, cap = capex(v2)
    en = simulate(df, kwp, 50.0, battery=True)
    be = breakeven_extra(v2, en, cap, kwp)
    v1 = res["V1"]["fin"]
    print(f"\nV2 break-even extra value (yr1): {be:,.0f} som = ${be/A['fx_som_usd']:,.0f}/yr")
    # value above V1: what storage must earn so V2 NPV = V1 NPV
    lo, hi = 0.0, 5e7
    for _ in range(100):
        mid = (lo + hi) / 2
        if finance(v2, en, cap, kwp, extra_value_som=mid)["npv_som"] < v1["npv_som"]:
            lo = mid
        else:
            hi = mid
    print(f"V2 extra value to match V1 NPV: {mid:,.0f} som = ${mid/A['fx_som_usd']:,.0f}/yr")

    # Sensitivity (V1 and V3 NPV / IRR)
    sens = []
    cases = [
        ("Base case", {}, {}),
        ("Tariff growth 0%", dict(esc_to_2030=0.0, esc_after=0.0), {}),
        ("Tariff growth 12% to 2030", dict(esc_to_2030=0.12), {}),
        ("Discount rate 10%", dict(discount=0.10), {}),
        ("Discount rate 18%", dict(discount=0.18), {}),
        ("Tax holiday 5 years", dict(tax_holiday=5), {}),
        ("Green loan 10% + tax holiday 5y", dict(discount=0.10, tax_holiday=5), {}),
        ("CAPEX -20%", {}, dict(module_usd_w=0.22*0.8, inv50_usd=3400*0.8, bos_usd_w=0.15*0.8, install_usd_w=0.12*0.8, luna215_usd=64000*0.8)),
        ("CAPEX +20%", {}, dict(module_usd_w=0.22*1.2, inv50_usd=3400*1.2, bos_usd_w=0.15*1.2, install_usd_w=0.12*1.2, luna215_usd=64000*1.2)),
        ("Yield 1,350 kWh/kWp", dict(yield_kwh_kwp=1350), {}),
        ("Yield 1,680 kWh/kWp (PVGIS)", dict(yield_kwh_kwp=1680), {}),
        ("KGS -20% vs USD", dict(fx_som_usd=87.45*1.2), {}),
    ]
    for label, ao, po in cases:
        rr = run(ao, po)
        sens.append(dict(case=label, **{f"{k}_npv_musd": round(rr[k]["fin"]["npv_som"] / A["fx_som_usd"] / 1000, 1)
                                        for k in rr},
                         **{f"{k}_irr": round(rr[k]["fin"]["irr"] * 100, 1) for k in rr}))
    sdf = pd.DataFrame(sens)
    print("\n", sdf.to_string(index=False))
    res["_sensitivity"] = sens
    res["_v2_breakeven_extra_som"] = round(be)
    res["_v2_match_v1_extra_som"] = round(mid)
    res["_monthly_pv_kwh_per_kwp"] = [round(x, 1) for x in monthly_pv_per_kwp()[0]]
    with open("results.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=float)

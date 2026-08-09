#!/usr/bin/env python3
"""Reverse-engineer Cody's volleyball model from his sheet (THRU 10/22).
Hypotheses to confirm:
  PPS = KPS + APS + BPS
  Z_Points = zscore(PPS)
  Z_SOS   = (mean_rank - SOS_rank)/sd(rank)   [tougher schedule (lower rank) => higher Z]
  Adj Score = Z_Points + 2*Z_SOS
Verify against his printed Z/Adj columns to catch transcription errors."""
import statistics as st

# team, KPS, APS, BPS, PPS, SOS_rank, SSF_rank, hisZp, hisZsos, hisAdj
R=[
("KENTUCKY",14.509,1.228,2.588,18.325,4,3,1.156,0.967,3.090),
("TEXAS",14.820,1.320,2.100,18.240,7,6,1.033,0.856,2.745),
("SMU",13.700,1.600,2.700,18.000,3,16,0.686,1.004,2.693),
("NEBRASKA",14.317,1.200,2.717,18.234,8,5,1.024,0.819,2.662),
("WISCONSIN",14.500,1.400,2.800,18.700,23,10,1.698,0.264,2.226),
("LOUISVILLE",13.760,1.340,2.960,18.060,11,14,0.772,0.708,2.188),
("PITT",13.440,1.440,2.660,17.540,1,8,0.020,1.078,2.176),
("CREIGHTON",13.700,2.100,2.400,18.200,15,13,0.975,0.560,2.094),
("STANFORD",14.328,1.627,2.366,18.321,21,20,1.150,0.338,1.825),
("ARIZONA STATE",13.453,1.516,2.859,17.828,13,27,0.437,0.634,1.704),
("TEXAS A&M",14.440,1.330,2.440,18.210,28,24,0.989,0.079,1.147),
("KANSAS",13.260,1.400,2.620,17.280,12,23,-0.356,0.671,0.986),
("TCU",13.760,1.400,2.290,17.450,16,18,-0.110,0.523,0.936),
("MIAMI",12.920,2.360,2.880,18.160,30,51,0.917,0.005,0.926),
("PENN STATE",13.268,1.437,1.944,16.649,2,1,-1.268,1.041,0.813),
("FLORIDA",13.320,1.240,2.350,16.910,9,9,-0.891,0.782,0.673),
("USC",13.270,1.300,2.810,17.380,19,12,-0.211,0.412,0.612),
("BAYLOR",13.290,1.480,2.390,17.160,17,21,-0.529,0.486,0.442),
("PURDUE",13.794,1.059,2.478,17.331,22,11,-0.282,0.301,0.319),
("ILLINOIS",13.400,1.700,2.300,17.400,24,7,-0.182,0.227,0.271),
("WASHINGTON",12.590,1.620,2.260,16.470,6,4,-1.527,0.893,0.258),
("MISSOURI",13.410,1.800,2.620,17.830,33,35,0.440,-0.106,0.227),
("UCLA",12.940,1.190,2.250,16.380,5,2,-1.658,0.930,0.202),
("INDIANA",13.680,1.540,2.680,17.900,35,28,0.541,-0.180,0.180),
("GEORGIA TECH",12.860,1.230,2.500,16.590,10,17,-1.354,0.745,0.136),
("MICHIGAN",13.760,1.490,2.330,17.580,32,29,0.078,-0.069,-0.061),
("ARIZONA",13.700,1.600,2.000,17.300,27,25,-0.327,0.116,-0.096),
("TENNESSEE",14.100,1.480,2.530,18.110,44,46,0.845,-0.514,-0.182),
("OREGON",13.250,1.710,2.380,17.340,42,31,-0.269,-0.439,-1.148),
("BYU",14.304,1.768,2.341,18.413,65,48,1.283,-1.291,-1.298),
("LSU",12.548,1.068,2.342,15.958,18,15,-2.268,0.449,-1.370),
("UTAH",12.630,1.390,2.100,16.120,26,26,-2.034,0.153,-1.728),
("MINNESOTA",12.780,1.630,2.650,17.060,45,22,-0.674,-0.551,-1.775),
("IOWA STATE",14.250,1.440,1.730,17.420,53,45,-0.153,-0.847,-1.847),
("COLORADO",13.150,1.580,2.500,17.230,54,47,-0.428,-0.884,-2.195),
("SAN DIEGO",12.600,1.300,2.400,16.300,48,68,-1.773,-0.662,-3.096),
("MICHIGAN STATE",13.400,1.900,2.130,17.430,73,44,-0.139,-1.587,-3.312),
("NORTH CAROLINA",13.730,1.170,2.920,17.820,82,52,0.425,-1.920,-3.415),
("UTEP",13.600,1.800,2.600,18.000,104,97,0.686,-2.734,-4.783),
("WESTERN KENTUCKY",14.470,1.400,2.540,18.410,118,119,1.279,-3.252,-5.226),
]
pps=[r[4] for r in R]; sos=[r[5] for r in R]
def z(x,xs,ddof): m=st.mean(xs); s=st.pstdev(xs) if ddof==0 else st.stdev(xs); return (x-m)/s,m,s
# find which ddof reproduces his Z best
for ddof in (0,1):
    err_p=err_s=0
    mp=st.mean(pps); ms=st.mean(sos)
    sp=st.pstdev(pps) if ddof==0 else st.stdev(pps)
    ss=st.pstdev(sos) if ddof==0 else st.stdev(sos)
    for r in R:
        zp=(r[4]-mp)/sp; zs=(ms-r[5])/ss
        err_p+=abs(zp-r[7]); err_s+=abs(zs-r[8])
    print(f"ddof={ddof}  meanPPS={mp:.3f} sdPPS={sp:.3f}  meanSOS={ms:.2f} sdSOS={ss:.2f}  |Zp err|={err_p:.3f} |Zsos err|={err_s:.3f}")

# reproduce Adj with best (ddof=1 sample) and check ranking
mp=st.mean(pps); sp=st.stdev(pps); ms=st.mean(sos); ss=st.stdev(sos)
rows=[]
for r in R:
    zp=(r[4]-mp)/sp; zs=(ms-r[5])/ss; adj=zp+2*zs
    rows.append((r[0],r[3],r[4],adj,r[9]))
print("\n rebuilt vs his Adj (top 8):")
for name,_,_,adj,his in rows[:8]:
    print(f"  {name:16s} rebuilt {adj:+.3f}  his {his:+.3f}  Δ {adj-his:+.3f}")
maxd=max(abs(a-h) for _,_,_,a,h in rows)
order_ok=[rows[i][0] for i in range(len(rows))]==[r[0] for r in sorted(rows,key=lambda x:-x[3])]
print(f"\n max|Δ Adj|={maxd:.3f}   his row order == sort by rebuilt Adj: {order_ok}")

# ---- emit fallback model JSON (raw inputs; Z/Adj computed at runtime so SOS weight is a live dial) ----
import json
CONF={ "KENTUCKY":"SEC","TEXAS":"SEC","SMU":"ACC","NEBRASKA":"Big Ten","WISCONSIN":"Big Ten",
 "LOUISVILLE":"ACC","PITT":"ACC","CREIGHTON":"Big East","STANFORD":"ACC","ARIZONA STATE":"Big 12",
 "TEXAS A&M":"SEC","KANSAS":"Big 12","TCU":"Big 12","MIAMI":"ACC","PENN STATE":"Big Ten",
 "FLORIDA":"SEC","USC":"Big Ten","BAYLOR":"Big 12","PURDUE":"Big Ten","ILLINOIS":"Big Ten",
 "WASHINGTON":"Big Ten","MISSOURI":"SEC","UCLA":"Big Ten","INDIANA":"Big Ten","GEORGIA TECH":"ACC",
 "MICHIGAN":"Big Ten","ARIZONA":"Big 12","TENNESSEE":"SEC","OREGON":"Big Ten","BYU":"Big 12",
 "LSU":"SEC","UTAH":"Big 12","MINNESOTA":"Big Ten","IOWA STATE":"Big 12","COLORADO":"Big 12",
 "SAN DIEGO":"WCC","MICHIGAN STATE":"Big Ten","NORTH CAROLINA":"ACC","UTEP":"CUSA","WESTERN KENTUCKY":"CUSA"}
teams=[{"team":r[0].title().replace("Smu","SMU").replace("Tcu","TCU").replace("Byu","BYU")
        .replace("Usc","USC").replace("Ucla","UCLA").replace("Lsu","LSU").replace("Utep","UTEP")
        .replace("A&M","A&M"),
        "conf":CONF.get(r[0]),"kps":r[1],"aps":r[2],"bps":r[3],"pps":r[4],
        "sos":r[5],"ssf":r[6]} for r in R]
out={"source":"Cody's model sheet","asof":"Thru Oct 22","sos_weight":2,"teams":teams}
json.dump(out,open("data/vb_model.json","w"),ensure_ascii=False,indent=1)
print("wrote data/vb_model.json teams=%d"%len(teams))

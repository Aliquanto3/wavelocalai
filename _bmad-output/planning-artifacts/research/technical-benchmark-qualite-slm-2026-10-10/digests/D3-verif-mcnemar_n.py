from statistics import NormalDist
from math import sqrt, ceil, comb
z=NormalDist().inv_cdf
za, zb = z(0.975), z(0.80)
def connor(d, psi): return ceil((za*sqrt(psi)+zb*sqrt(psi-d*d))**2/d**2)
def miller(d, psi): return ceil((za+zb)**2*(psi-d*d)/d**2)
def unpaired(p1,p2):
    pb=(p1+p2)/2
    return ceil((za*sqrt(2*pb*(1-pb))+zb*sqrt(p1*(1-p1)+p2*(1-p2)))**2/(p1-p2)**2)
def exact_power(n,d,psi,alpha=0.05):
    # exact conditional binomial test; discordant count m ~ Bin(n,psi), b|m ~ Bin(m, p) with p=(psi+d)/(2psi)
    p=(psi+d)/(2*psi); pw=0
    for m in range(n+1):
        pm=comb(n,m)*psi**m*(1-psi)**(n-m)
        if pm<1e-12 or m==0: continue
        # two-sided exact test under H0 p=.5: reject set
        pmf0=[comb(m,k)*0.5**m for k in range(m+1)]
        rej=0
        for k in range(m+1):
            pv=sum(x for x in pmf0 if x<=pmf0[k]*(1+1e-9))
            if pv<=alpha: rej+=comb(m,k)*p**k*(1-p)**(m-k)
        pw+=pm*rej
    return pw
def exact_n(d,psi):
    n=max(10,connor(d,psi)-20)
    while exact_power(n,d,psi)<0.8: n+=1
    return n
for d,(p1,p2) in [(0.10,(0.6,0.7)),(0.20,(0.5,0.7))]:
    for psi in (0.2,0.3,0.4):
        print(f"d={d} psi={psi} connor={connor(d,psi)} miller={miller(d,psi)} exact={exact_n(d,psi)}")
    print("unpaired",unpaired(p1,p2))
for d in (0.10,0.20):
    for psi in (0.2,0.4):
        print(f"N=30 d={d} psi={psi} power_exact={exact_power(30,d,psi):.2f}")

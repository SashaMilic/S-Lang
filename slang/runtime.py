
import math, cmath
import numpy as np

H = (1/ math.sqrt(2)) * np.array([[1, 1], [1, -1]], dtype=np.complex128)
X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)

def Rz(theta: float) -> np.ndarray:
    return np.array([[cmath.exp(-1j*theta/2), 0], [0, cmath.exp(1j*theta/2)]], dtype=np.complex128)

CNOT_4 = np.array([[1,0,0,0],[0,1,0,0],[0,0,0,1],[0,0,1,0]], dtype=np.complex128)

class StateVector:
    def __init__(self, n):
        self.n=n; self.state=np.zeros(1<<n, dtype=np.complex128); self.state[0]=1+0j
    def apply_single(self, q, U):
        n=self.n; mask=1<<q; vec=self.state
        a00,a01,a10,a11=U[0,0],U[0,1],U[1,0],U[1,1]
        for i in range(0,1<<n):
            if (i & mask)==0:
                j=i|mask; v0,v1=vec[i], vec[j]
                vec[i]=a00*v0 + a01*v1
                vec[j]=a10*v0 + a11*v1
    def apply_two(self, q1, q2, U):
        if q1==q2: raise ValueError("two-qubit op needs distinct qubits")
        q_low,q_high=(q1,q2) if q1<q2 else (q2,q1)
        n=self.n; mask_low=1<<q_low; mask_high=1<<q_high; vec=self.state
        for base in range(0,1<<n):
            if (base & mask_low) or (base & mask_high): continue
            i00=base; i01=base|mask_low; i10=base|mask_high; i11=base|mask_high|mask_low
            v=np.array([vec[i00],vec[i01],vec[i10],vec[i11]], dtype=np.complex128)
            v2=U @ v; vec[i00],vec[i01],vec[i10],vec[i11]=v2[0],v2[1],v2[2],v2[3]
    def sample_all(self, shots):
        probs=(self.state.real**2 + self.state.imag**2); probs=probs/np.sum(probs)
        outcomes = np.random.choice(len(probs), size=shots, p=probs)
        from collections import Counter
        counts=Counter()
        for idx in outcomes: counts[format(idx, f"0{self.n}b")]+=1
        return counts

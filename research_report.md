# Module 3: Securing Quantum Channel — Research Report

## 1. The BB84 Protocol

### Overview
BB84, proposed by Bennett and Brassard in 1984, is the first and most widely implemented
Quantum Key Distribution (QKD) protocol. It exploits two fundamental quantum mechanical
properties to achieve information-theoretic security:

- **No-cloning theorem**: An unknown quantum state cannot be perfectly copied.
- **Measurement disturbance**: Measuring a quantum state in the wrong basis irreversibly
  disturbs it.

### Protocol Steps

| Step | Action |
|------|--------|
| 1 | Alice generates a random bit string and a random basis string (rectilinear `+` or diagonal `×`). |
| 2 | She encodes each bit as a qubit: `0`→`|0⟩`/`|+⟩`, `1`→`|1⟩`/`|-⟩` depending on basis. |
| 3 | She sends the qubits to Bob over the quantum channel. |
| 4 | Bob randomly chooses a measurement basis for each qubit. |
| 5 | Alice and Bob publicly compare *bases* (not bits) over a classical channel. |
| 6 | They keep only the bits where their bases matched — the **sifted key**. |
| 7 | They sacrifice a random subset of the sifted key to estimate the **QBER**. |
| 8 | If QBER < threshold, they apply error correction and privacy amplification to get the final secure key. |

### Encoding Table

```
Basis  Bit  State
  +     0   |0⟩  (horizontal)
  +     1   |1⟩  (vertical)
  ×     0   |+⟩  (diagonal 45°)
  ×     1   |-⟩  (diagonal 135°)
```

---

## 2. Quantum Bit Error Rate (QBER)

### Definition
QBER is the fraction of sifted key bits that differ between Alice and Bob:

```
QBER = (number of mismatched sifted bits) / (total sifted bits)
```

### Role in Security
In a noiseless, eavesdropper-free channel, QBER ≈ 0%.

When Eve performs an **intercept-resend** attack (the simplest attack):
- She measures each qubit in a random basis.
- She guesses the correct basis with probability 1/2.
- When she guesses wrong, she collapses the qubit into the wrong state.
- Bob then measures the re-sent qubit; even if he picks the right basis, the
  disturbed qubit yields an error with probability 1/2.
- Net error contribution per qubit from Eve: **25%** (if Eve intercepts all qubits).

### QBER Threshold

The theoretical QBER abort threshold for BB84 is **11%** under the most general
(coherent) attacks when using standard error correction + privacy amplification.

| QBER range | Interpretation |
|------------|---------------|
| 0 – 5%     | Low noise, likely no eavesdropper; secure key can be distilled |
| 5 – 11%    | Elevated noise; error correction + privacy amplification still feasible |
| > 11%      | Abort — Eve could hold more information than Alice and Bob can eliminate |
| ~25%       | Full intercept-resend attack by Eve (intercepting 100% of qubits) |

The 11% value comes from the security proof by Shor & Preskill (2000), which
showed that BB84 is secure as long as the QBER is below this threshold (assuming
one-way classical post-processing). With two-way reconciliation, the threshold
rises to ~18.9%.

### Partial Intercept Attack
If Eve intercepts only a fraction *f* of qubits:

```
QBER ≈ f × 0.25
```

So Eve must intercept > 44% of qubits before the QBER exceeds 11%.

---

## 3. Quantum Temporal Authentication (QTA)

### The Man-in-the-Middle Problem
In a classical network, a Man-in-the-Middle (MitM) attacker can impersonate both
parties. In QKD, an authenticated classical channel is required to prevent this —
but *authentication itself* traditionally relies on a pre-shared secret.

QTA offers an alternative or supplement: it verifies the **arrival time** of photons
at the nanosecond (or even picosecond) scale to detect relay attacks.

### How QTA Works

1. **Synchronized clocks**: Alice and Bob use quantum-synchronized clocks (e.g., via
   entangled photon pairs or GPS-disciplined oscillators) accurate to < 1 ns.
2. **Expected arrival window**: Given the known fiber length (speed of light in fiber
   ≈ 2×10⁸ m/s), each photon has a predicted arrival time with a tolerance window
   of a few nanoseconds.
3. **Temporal tagging**: Each photon is timestamped on arrival.
4. **Anomaly detection**: Any photon arriving outside the tolerance window — or with
   an anomalous pattern — is flagged.

### Why QTA Defeats MitM
A MitM attacker (Eve) must:
1. **Intercept** Alice's photon — this takes time (even a beamsplitter introduces
   nanosecond-scale delays).
2. **Measure** the qubit state — quantum measurement is not instantaneous; real
   detectors have dead times of 1–100 ns.
3. **Re-emit** a new photon toward Bob.

The total round-trip delay Eve introduces is typically **10–100 ns** or more.
With QTA enforcing a ±2 ns arrival window, Eve's relay is detectable regardless
of whether she disturbs the quantum state.

### QTA + BB84 Combined Defense
| Threat | Defeated by |
|--------|-------------|
| Passive eavesdropping (intercept-resend) | QBER elevation (BB84) |
| Photon-number splitting attack | Decoy states + QBER |
| Relay / MitM impersonation | QTA arrival-time verification |
| Slow relay (Eve uses quantum memory) | Sub-ns clock synchronization |

### Nanosecond Scale Justification
- Light travels ~20 cm in 1 ns in vacuum (~13 cm in fiber).
- Eve needs at minimum ~0.5 m of extra path for detection hardware.
- That equals ~3–5 ns of unavoidable delay.
- Modern superconducting nanowire single-photon detectors (SNSPDs) achieve
  timing jitter < 50 ps, making 1 ns resolution realistic.

---

## 4. Summary

BB84 provides security through QBER monitoring: any eavesdropping that disturbs
qubits raises the QBER above the 11% threshold, forcing Alice and Bob to abort.
QTA adds a complementary layer by verifying photon arrival times at nanosecond
precision, closing the relay/MitM attack vector that QBER alone cannot address.
Together, they form a robust two-layer defense for quantum key distribution.

---
*References*: Bennett & Brassard (1984); Shor & Preskill (2000); Gisin et al.,
Rev. Mod. Phys. 74 (2002); Vallone et al., PRL 115 (2015) [QTA timing].
